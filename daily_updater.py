#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股每日增量更新服务 - urllib并发版
- 30线程并发抓取（urllib.request）
- 无延迟，批量写库
- 每天凌晨6点自动更新

启动：python3 daily_updater.py --daemon
测试：curl http://localhost:5002/update
"""
import os, sys, time, json, datetime, warnings, threading, urllib.request, mysql.connector, uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
warnings.filterwarnings("ignore")

# ===================== 微信通知 =====================
WECOM_ACCOUNT_ID = "74491c177aed-im-bot"
WECOM_TO = "o9cq805NMM4qcns7e6FGqlKotkDk@im.wechat"
QUEUE_DIR = "/root/.openclaw/delivery-queue"

def notify_wechat(text):
    """向微信发送通知（写入 delivery-queue 由 Gateway 处理）"""
    entry = {
        "id": str(uuid.uuid4()),
        "enqueuedAt": int(time.time() * 1000),
        "channel": "openclaw-weixin",
        "to": WECOM_TO,
        "payloads": [{"text": text, "replyToTag": False, "replyToCurrent": False, "audioAsVoice": False}],
        "gifPlayback": False,
        "accountId": WECOM_ACCOUNT_ID,
        "retryCount": 0,
        "lastAttemptAt": 0,
    }
    os.makedirs(QUEUE_DIR, exist_ok=True)
    path = os.path.join(QUEUE_DIR, entry["id"] + ".json")
    with open(path, "w") as f:
        json.dump(entry, f, ensure_ascii=False)
    print(f"  📲 微信通知已入队: {text[:30]}...", flush=True)

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "OpenClaw@2026",
    "database": "a_stock_data",
    "charset": "utf8mb4"
}
PORT = 5002
FETCH_WORKERS = 10   # 10线程，避免触发东财API限速

# ===================== HTTP工具 =====================
def http_get(url, timeout=10):
    h = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://finance.eastmoney.com/",
    }
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except:
        return None

# ===================== DB工具 =====================
def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def sf(v):
    try:
        f = float(v) if v and str(v).strip() not in ("", "nan", "None") else None
        return round(f, 4) if f is not None else None
    except:
        return None

def si(v):
    try:
        return int(float(v)) if v and str(v).strip() not in ("", "nan", "None") else None
    except:
        return None

# ===================== 数据源（腾讯财经）=====================
def tencent_kline(ts_code, days=5):
    """腾讯财经K线接口，主力数据源"""
    sym, mkt = ts_code.split(".")
    mkt_map = {"SH": "sh", "SZ": "sz"}
    t_sym = mkt_map.get(mkt, mkt.lower()) + sym.lower()
    today = datetime.date.today()
    s = (today - datetime.timedelta(days=days * 2)).strftime("%Y-%m-%d")
    e = today.strftime("%Y-%m-%d")
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={t_sym},day,{s},{e},{days},qfq")
    txt = http_get(url)
    if not txt:
        return []
    try:
        idx = txt.index("{")
        data = json.loads(txt[idx:])
        klines = data["data"][t_sym]["qfqday"]
    except:
        return []
    result = []
    for k in klines:
        if len(k) < 6:
            continue
        try:
            open_p = float(k[1])
            close_p = float(k[2])
            pct = round((close_p - open_p) / open_p * 100, 2) if open_p else 0.0
            result.append({
                "date": k[0],
                "open": open_p, "close": close_p,
                "high": float(k[3]), "low": float(k[4]),
                "volume": int(float(k[5])),
                "amount": 0.0,
                "pct": pct,
            })
        except:
            continue
    return result

def em_kline(ts_code, days=5):
    """东方财富K线（备用）"""
    sym, mkt = ts_code.split(".")
    secid = ("1." + sym) if mkt == "SH" else ("0." + sym)
    today = datetime.date.today()
    s = (today - datetime.timedelta(days=days * 2)).strftime("%Y%m%d")
    e = today.strftime("%Y%m%d")
    url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid={secid}&fields1=f1,f2,f3,f4,f5"
           f"&fields2=f51,f52,f53,f54,f55,f56"
           f"&klt=101&fqt=1&beg={s}&end={e}&lmt={days}")
    txt = http_get(url)
    if not txt:
        return []
    try:
        j = json.loads(txt)
        kls = j.get("data", {}).get("klines", []) or []
    except:
        return []
    result = []
    for kl in kls:
        p = kl.split(",")
        if len(p) < 7:
            continue
        try:
            result.append({
                "date": p[0],
                "open": sf(p[1]), "close": sf(p[2]),
                "high": sf(p[3]), "low": sf(p[4]),
                "volume": si(p[5]), "amount": sf(p[6]),
                "pct": sf(p[8]) if len(p) > 8 else 0.0,
            })
        except:
            continue
    return result

# ===================== 记录准备 =====================
def prepare_records(ts_code, klines):
    if not klines:
        return []
    # 确保klines按日期正序（东方财富可能返回倒序）
    try:
        klines = sorted(klines, key=lambda x: x.get("date", ""))
    except Exception:
        pass
    closes_for_ma = []
    pcts_history = []   # 近5日涨幅历史
    vols_history = []   # 近20日成交量历史
    records = []
    for raw in klines:
        try:
            td = datetime.datetime.strptime(raw["date"], "%Y-%m-%d").date()
        except:
            continue
        close = raw.get("close")
        if close is None:
            continue
        volume = raw.get("volume") or 0
        closes_for_ma.append(close)
        pcts_history.append(raw.get("pct") or 0)
        vols_history.append(volume)
        n = len(closes_for_ma)

        ma5  = round(sum(closes_for_ma[-5:]) / min(5, n), 2)  if n >= 5  else None
        ma10 = round(sum(closes_for_ma[-10:]) / min(10, n), 2) if n >= 10 else None
        ma20 = round(sum(closes_for_ma[-20:]) / min(20, n), 2) if n >= 20 else None
        ma60 = round(sum(closes_for_ma[-60:]) / min(60, n), 2) if n >= 60 else None
        ma120 = ma60; ma250 = ma60
        lb = closes_for_ma[-20:-1] if len(closes_for_ma) > 1 else closes_for_ma[-20:]
        s1 = round(min(lb) * 0.98, 2) if lb else None
        s2 = round(min(lb) * 0.95, 2) if lb else None
        s3 = round(min(lb) * 0.92, 2) if lb else None
        p1 = round(max(lb) * 1.02, 2) if lb else None
        p2 = round(max(lb) * 1.05, 2) if lb else None
        p3 = round(max(lb) * 1.08, 2) if lb else None
        pct = raw.get("pct") or 0

        # 近5日累计涨幅（包含今日）
        rise_5d = round(sum(pcts_history[-5:]), 4) if n >= 1 else 0.0
        # 近20日均量（包含今日）
        avg_vol_20 = round(sum(vols_history[-20:]) / min(20, n), 2) if n >= 1 else 0.0
        # 近20日最高收盘价（包含今日）
        high_20d = round(max(closes_for_ma[-20:]), 2) if n >= 1 else close

        rd = 1 if pct > 0 else 0
        fd = 1 if pct < 0 else 0
        rtp = pct if pct > 0 else 0.0
        fdp = pct if pct < 0 else 0.0

        # 计算连涨/连跌：回看上一条记录
        if records:
            prev_rd = records[-1][9]
            prev_fd = records[-1][10]
            if prev_rd > 0 and pct > 0:
                rd = prev_rd + 1
            elif pct <= 0:
                rd = 0
            if prev_fd > 0 and pct < 0:
                fd = prev_fd + 1
            elif pct >= 0:
                fd = 0

        b5  = 1 if (ma5  and close < ma5)  else 0
        b10 = 1 if (ma10 and close < ma10) else 0
        b20 = 1 if (ma20 and close < ma20) else 0
        b60 = 1 if (ma60 and close < ma60) else 0
        bs1 = 1 if (s1  and close < s1)  else 0
        bp1 = 1 if (p1  and close > p1)  else 0
        records.append((
            ts_code, td, raw.get("open"), close, raw.get("high"), raw.get("low"),
            volume, raw.get("amount"), pct,
            rd, fd, rtp, fdp, ma5, ma10, ma20, ma60, ma120, ma250,
            s1, s2, s3, p1, p2, p3, b5, b10, b20, b60, bs1, bp1,
            rise_5d, avg_vol_20, high_20d
        ))
    return records

# ===================== 批量写入 =====================
def batch_upsert(conn, records):
    if not records:
        return 0
    sql = ("INSERT INTO stock_daily_price (ts_code,trade_date,open,close,high,low,volume,amount,pct_change,"
           "rise_days,fall_days,rise_total_pct,fall_total_pct,"
           "ma5,ma10,ma20,ma60,ma120,ma250,"
           "support_1,support_2,support_3,pressure_1,pressure_2,pressure_3,"
           "break_ma5,break_ma10,break_ma20,break_ma60,break_support1,break_pressure1,"
           "rise_5d,avg_vol_20,high_20d "
           ") VALUES ("
           "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
           "ON DUPLICATE KEY UPDATE "
           "open=VALUES(open),close=VALUES(close),high=VALUES(high),low=VALUES(low),"
           "volume=VALUES(volume),amount=VALUES(amount),pct_change=VALUES(pct_change),"
           "rise_days=VALUES(rise_days),fall_days=VALUES(fall_days),"
           "rise_total_pct=VALUES(rise_total_pct),fall_total_pct=VALUES(fall_total_pct),"
           "ma5=VALUES(ma5),ma10=VALUES(ma10),ma20=VALUES(ma20),ma60=VALUES(ma60),"
           "ma120=VALUES(ma120),ma250=VALUES(ma250),"
           "support_1=VALUES(support_1),support_2=VALUES(support_2),support_3=VALUES(support_3),"
           "pressure_1=VALUES(pressure_1),pressure_2=VALUES(pressure_2),pressure_3=VALUES(pressure_3),"
           "break_ma5=VALUES(break_ma5),break_ma10=VALUES(break_ma10),"
           "break_ma20=VALUES(break_ma20),break_ma60=VALUES(break_ma60),"
           "break_support1=VALUES(break_support1),break_pressure1=VALUES(break_pressure1),"
           "rise_5d=VALUES(rise_5d),avg_vol_20=VALUES(avg_vol_20),high_20d=VALUES(high_20d),"
           "updated_at=NOW()")
    c = conn.cursor()
    total = 0
    try:
        for vals in records:
            c.execute(sql, vals)
            total += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        c.close()
    return total

# ===================== 主逻辑 =====================
_fetch_lock = threading.Lock()
_fetch_done = 0
_fetch_total = 0

def run_daily_update(log=True):
    global _fetch_done, _fetch_total
    _fetch_done = 0

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if log:
        print(f"[{ts}] 🚀 启动每日A股数据更新（{FETCH_WORKERS}线程并发）...", flush=True)

    # 开始前发微信
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    notify_wechat(f"📡 【A股数据更新开始】\n日期：{today_str}\n状态：正在抓取股票数据，请稍候...")

    # 获取股票列表
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT ts_code, symbol, name FROM stock_basic WHERE is_active=1")
    stocks = [{"ts_code": r[0], "symbol": r[1], "name": r[2]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    _fetch_total = len(stocks)

    if log:
        print(f"  共 {stocks.__len__()} 只股票，开始并发抓取...", flush=True)

    results = []  # [(ts_code, name, records), ...]
    res_lock = threading.Lock()
    done_count = [0]

    def fetch_one(stk):
        global _fetch_done
        ts_code = stk["ts_code"]
        name = stk["name"]
        klines = tencent_kline(ts_code, days=5)
        if not klines:
            klines = em_kline(ts_code, days=5)
        records = prepare_records(ts_code, klines)
        with res_lock:
            results.append((ts_code, name, records))
            done_count[0] += 1
            if log and done_count[0] % 500 == 0:
                print(f"  抓取进度: {done_count[0]}/{_fetch_total}", flush=True)
        return ts_code, name, records

    # 并发抓取
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        futures = [executor.submit(fetch_one, stk) for stk in stocks]
        for future in as_completed(futures):
            pass  # 等待全部完成

    ok_count = sum(1 for _, _, r in results if r)
    fail_count = len(results) - ok_count
    all_records = []
    for _, _, recs in results:
        all_records.extend(recs)

    if log:
        print(f"  抓取完成 ✅ 成功 {ok_count}，失败 {fail_count}，共 {len(all_records)} 条记录", flush=True)
        print(f"  开始写入数据库...", flush=True)

    # 批量写库
    conn = get_db()
    BATCH = 500
    written = 0
    for i in range(0, len(all_records), BATCH):
        batch = all_records[i:i+BATCH]
        n = batch_upsert(conn, batch)
        written += n
        if log:
            print(f"  写入 [{i//BATCH+1}/{(len(all_records)-1)//BATCH+1}] +{n}条", flush=True)
    conn.close()

    msg = f"完成！成功 {ok_count} 只，失败 {fail_count} 只，写入 {written} 条"
    if log:
        print(f"[{ts}] {msg}", flush=True)

    # 更新完成后发微信
    notify_wechat(f"✅ 【A股数据更新完成】\n日期：{today_str}\n成功：{ok_count} 只\n失败：{fail_count} 只\n写入：{written} 条\n最新数据已同步！")

    return msg

# ===================== HTTP服务 =====================
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path in ("/update", "/update/"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            try:
                result = run_daily_update(log=True)
                self.wfile.write(f"OK: {result}".encode("utf-8"))
            except Exception as e:
                import traceback; traceback.print_exc()
                self.wfile.write(f"ERROR: {e}".encode("utf-8"))
        elif self.path in ("/status", "/status/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            try:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM stock_basic WHERE is_active=1")
                basic = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM stock_daily_price")
                price = cur.fetchone()[0]
                cur.execute("SELECT MAX(trade_date) FROM stock_daily_price")
                last_date = cur.fetchone()[0]
                cur.execute("SELECT COUNT(DISTINCT ts_code) FROM stock_daily_price WHERE trade_date=%s", (datetime.date.today(),))
                today_cnt = cur.fetchone()[0]
                conn.close()
                info = {"stocks": basic, "price_records": price, "last_update": str(last_date), "today": today_cnt}
                self.wfile.write(json.dumps(info, ensure_ascii=False, indent=2).encode("utf-8"))
            except Exception as e:
                self.wfile.write(f'{{"error": "{e}"}}'.encode("utf-8"))
        elif self.path in ("/health", "/health/"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        self.do_GET()

def auto_daily():
    print("⏰ 每日自动更新已启动，每天 06:00 执行", flush=True)
    import sched as _sched
    _lock = threading.Lock()
    _scheduler = _sched.scheduler(time.time, time.sleep)

    def job():
        with _lock:
            print("\n" + "=" * 50, flush=True)
            print("  🌅 定时任务：每日A股数据更新", flush=True)
            print("=" * 50, flush=True)
            try:
                run_daily_update(log=True)
            except Exception as e:
                print(f"  出错: {e}", flush=True)
        _schedule_next()

    def _schedule_next():
        now = datetime.datetime.now()
        target = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if now.hour >= 6:
            target += datetime.timedelta(days=1)
        delay = (target - now).total_seconds()
        _scheduler.enter(delay, 1, job, ())

    _schedule_next()
    while True:
        _scheduler.run(blocking=True)

if __name__ == "__main__":
    if "--once" in sys.argv:
        result = run_daily_update(log=True)
        print(result)
    elif "--daemon" in sys.argv:
        server = HTTPServer(("0.0.0.0", PORT), Handler)
        print(f"🌅 A股每日更新服务启动，监听 http://0.0.0.0:{PORT}", flush=True)
        t = threading.Thread(target=auto_daily, daemon=True)
        t.start()
        server.serve_forever()
    else:
        print("用法：")
        print("  python3 daily_updater.py --daemon   # 常驻服务")
        print("  python3 daily_updater.py --once   # 单次执行")
