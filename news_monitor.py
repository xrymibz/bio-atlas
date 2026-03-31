#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
先正达( Syngenta )上市新闻监控
- 监控国内外财经新闻源
- 有新文章立即推送微信
- 每天定期搜索 + 有新消息随时推送

启动：python3 news_monitor.py --once  (手动触发一次)
      python3 news_monitor.py --daemon (后台常驻定时监控)
"""
import os, sys, time, json, datetime, re, urllib.request, sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# ===================== 配置 =====================
STATE_FILE = "/root/.openclaw/workspace/news_monitor_state.json"
KEYWORDS = ["先正达", "Syngenta", "先正达集团", "先正达IPO", "先正达上市"]
PUSH_THRESHOLD_HOURS = 6   # 超过6小时没推送就强制推送一次
DAEMON_INTERVAL = 3 * 3600  # 每3小时搜索一次

# ===================== HTTP工具 =====================
def fetch(url, headers=None, enc="utf-8", timeout=10):
    h = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode(enc, errors="ignore")
    except Exception as e:
        return None

# ===================== 新闻源 =====================
def search_eastmoney():
    """东方财富快讯（主力源），扫描20页约400条快讯"""
    articles = []
    for page in range(1, 21):
        url = f"https://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_20_{page}_.html"
        txt = fetch(url)
        if not txt:
            continue
        try:
            m = re.search(r'ajaxResult\s*=\s*(\{.*?\})\s*$', txt, re.DOTALL)
            if not m:
                continue
            data = json.loads(m.group(1))
            items = data.get("LivesList", [])
            for a in items:
                title = a.get("title", "")
                url_link = a.get("url_w", "") or a.get("url_m", "")
                showtime = a.get("showtime", "")
                if title and url_link:
                    articles.append({
                        "title": title.strip(),
                        "url": url_link,
                        "source": "东方财富",
                        "ctime": showtime[:16] if showtime else "",
                    })
        except:
            continue
    return articles

def search_sina():
    """新浪财经快讯（备用源）"""
    articles = []
    # 新浪快讯-feed接口
    url = f"https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2517&k=%E5%85%88%E6%AD%A3%E8%BE%BE&num=50&page=1&r={time.time()}"
    txt = fetch(url)
    if txt:
        try:
            data = json.loads(txt)
            items = data.get("result", {}).get("data", [])
            for a in items:
                title = a.get("title", "")
                url_link = a.get("url", "")
                ctime = a.get("ctime", "")
                if title and url_link:
                    articles.append({
                        "title": title.strip(),
                        "url": url_link,
                        "source": "新浪财经",
                        "ctime": datetime.datetime.fromtimestamp(int(ctime)).strftime("%Y-%m-%d %H:%M") if ctime else "",
                    })
        except:
            pass
    return articles

# ===================== 状态管理 =====================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"seen_ids": [], "last_push": None, "last_check": None}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def make_article_id(article):
    """生成文章唯一ID（用标题+来源）"""
    s = f"{article['source']}:{article['title']}"
    import hashlib
    return hashlib.md5(s.encode()).hexdigest()[:16]

def is_relevant(article):
    """判断文章是否与先正达相关"""
    text = article["title"]
    keywords_any = ["先正达", "syngenta", "Syngenta", "先正达集团"]
    return any(kw.lower() in text.lower() for kw in keywords_any)

# ===================== 主搜索逻辑 =====================
def search_all():
    """从所有源搜索，返回与先正达相关的新文章"""
    all_articles = []
    sources = [
        ("eastmoney", search_eastmoney),
        ("sina", search_sina),
    ]
    for name, func in sources:
        try:
            arts = func()
            if arts:
                all_articles.extend(arts)
                print(f"  [{name}] 找到 {len(arts)} 条", flush=True)
        except Exception as e:
            print(f"  [{name}] 出错: {e}", flush=True)
    return all_articles

def check_and_push():
    """检查新文章，有新内容则返回（供外部推送）"""
    state = load_state()
    seen_ids = set(state.get("seen_ids", []))
    
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始搜索先正达相关新闻...", flush=True)
    articles = search_all()
    
    new_articles = [a for a in articles if is_relevant(a) and make_article_id(a) not in seen_ids]
    
    print(f"  相关文章: {len(articles)} 条, 新文章: {len(new_articles)} 条", flush=True)
    
    if new_articles:
        # 更新已见ID
        for a in new_articles:
            seen_ids.add(make_article_id(a))
        state["seen_ids"] = list(seen_ids)[-500:]  # 保留最近500条
        state["last_push"] = datetime.datetime.now().isoformat()
        save_state(state)
        return new_articles
    
    # 强制推送检查（超过阈值）
    last_push = state.get("last_push")
    if last_push:
        last_push_time = datetime.datetime.fromisoformat(last_push)
        hours_since = (datetime.datetime.now() - last_push_time).total_seconds() / 3600
        if hours_since >= PUSH_THRESHOLD_HOURS:
            print(f"  已{hours_since:.1f}小时无推送，发送心跳", flush=True)
            state["last_check"] = datetime.datetime.now().isoformat()
            save_state(state)
            return []  # 返回空表示只有心跳，不推送文章
    else:
        state["last_check"] = datetime.datetime.now().isoformat()
        save_state(state)
    
    return new_articles

def format_articles_message(articles):
    """格式化文章列表为微信消息"""
    lines = [f"📰 **先正达上市相关新闻**（{len(articles)} 条）\n"]
    for i, a in enumerate(articles[:10], 1):
        ctime = a.get("ctime", "")
        lines.append(f"{i}. {a['title']}")
        if ctime:
            lines.append(f"   🕐 {ctime} | {a['source']}")
        else:
            lines.append(f"   📌 {a['source']}")
        lines.append(f"   🔗 {a['url']}")
        lines.append("")
    if len(articles) > 10:
        lines.append(f"……还有 {len(articles)-10} 条，点击链接查看全部")
    return "\n".join(lines)

# ===================== HTTP服务 =====================
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path in ("/check", "/check/"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            try:
                new_arts = check_and_push()
                if new_arts:
                    msg = format_articles_message(new_arts)
                    self.wfile.write(f"NEW: {len(new_arts)} articles\n\n{msg}".encode("utf-8"))
                else:
                    self.wfile.write(b"NO_NEW_ARTICLES")
            except Exception as e:
                import traceback; traceback.print_exc()
                self.wfile.write(f"ERROR: {e}".encode("utf-8"))
        elif self.path in ("/health", "/health/"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        elif self.path in ("/status", "/status/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            state = load_state()
            self.wfile.write(json.dumps({
                "seen_count": len(state.get("seen_ids", [])),
                "last_push": state.get("last_push"),
                "last_check": state.get("last_check"),
            }, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

def run_daemon(port=5003):
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"📰 先正达新闻监控启动，监听 http://0.0.0.0:{port}", flush=True)
    print(f"   GET /check   - 触发一次搜索检查", flush=True)
    print(f"   GET /status  - 查看状态", flush=True)
    print(f"   GET /health  - 健康检查", flush=True)
    
    # 定时搜索线程
    def schedule_loop():
        while True:
            time.sleep(DAEMON_INTERVAL)
            print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ 定时检查...", flush=True)
            try:
                check_and_push()
            except Exception as e:
                print(f"  检查出错: {e}", flush=True)
    
    t = threading.Thread(target=schedule_loop, daemon=True)
    t.start()
    server.serve_forever()

if __name__ == "__main__":
    if "--once" in sys.argv:
        result = check_and_push()
        if result:
            print("\n" + format_articles_message(result))
        else:
            print("没有新文章")
    elif "--daemon" in sys.argv:
        run_daemon()
    else:
        print("用法：")
        print("  python3 news_monitor.py --once    # 手动触发一次搜索")
        print("  python3 news_monitor.py --daemon # 常驻监控服务")
