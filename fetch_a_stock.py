#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股数据采集脚本 v3（主备数据源）
主源：东方财富 push2his
备源：新浪财经 CN_MarketData

用法：
  python3 fetch_a_stock.py --basic   # 仅采集股票基础信息
  python3 fetch_a_stock.py --all    # 全量采集（基础+行情）
  python3 fetch_a_stock.py --daily   # 每日增量（最近5天）
  python3 fetch_a_stock.py --resume  # 断点续传
  python3 fetch_a_stock.py 000001.SZ  # 单只股票
"""

import os, sys, time, json, datetime, warnings, urllib.request, mysql.connector
warnings.filterwarnings("ignore")

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "OpenClaw@2026",
    "database": "a_stock_data",
    "charset": "utf8mb4"
}
STATE_FILE = "/root/.openclaw/workspace/a_stock_state.json"
GAP = 1.5
RETRY_GAP = 5
MAX_RETRIES = 3

# HTTP工具
def http_get(url, headers=None, enc="utf-8", timeout=10):
    h = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://finance.eastmoney.com/",
    }
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = r.read()
            return d.decode(enc if enc == "gbk" else "utf-8", errors="ignore")
    except:
        return None

# DB工具
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

def upsert(conn, sql, vals):
    c = conn.cursor()
    try:
        c.execute(sql, vals)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        if e.errno not in (1062,):
            pass
        return False
    finally:
        c.close()

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE))
        except:
            pass
    return {"idx": 0, "done": [], "basic_done": False}

def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f)

# ===== 数据源1：东方财富 K线（主） =====
def em_kline(ts_code, days=60):
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
                "open": sf(p[1]),
                "close": sf(p[2]),
                "high": sf(p[3]),
                "low": sf(p[4]),
                "volume": si(p[5]),
                "amount": sf(p[6]),
                "pct": sf(p[8]) if len(p) > 8 else 0.0,
            })
        except:
            continue
    return result

# ===== 数据源2：新浪 K线（备） =====
def sina_kline(ts_code, days=30):
    sym, mkt = ts_code.split(".")
    sym2 = mkt.lower() + sym
    url = (f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php"
           f"/CN_MarketData.getKLineData?symbol={sym2}&scale=240&ma=5&datalen={days}")
    txt = http_get(url, enc="utf-8")
    if not txt:
        return []
    try:
        data = json.loads(txt)
    except:
        return []
    result = []
    for item in (data or []):
        try:
            result.append({
                "date": item.get("day", ""),
                "open": sf(item.get("open")),
                "close": sf(item.get("close")),
                "high": sf(item.get("high")),
                "low": sf(item.get("low")),
                "volume": si(item.get("volume")),
                "amount": sf(item.get("ma_price5")),
                "pct": 0.0,
            })
        except:
            continue
    return result

# ===== 数据源3：新浪实时（批量） =====
def sina_realtime(ts_list):
    if not ts_list:
        return {}
    syms = ",".join(
        ("sh" if t.endswith(".SH") else "sz") + t.split(".")[0]
        for t in ts_list
    )
    url = f"https://hq.sinajs.cn/list={syms}"
    txt = http_get(url, headers={"Referer": "https://finance.sina.com.cn"}, enc="gbk")
    if not txt:
        return {}
    result = {}
    for line in txt.split("\n"):
        if "=" not in line:
            continue
        try:
            raw = line.strip().split("=")[1].strip('";\n ')
            parts = raw.split(",")
            if len(parts) < 10:
                continue
            rs = line.split("_")[0].split("hq_str_")[1]
            sym = rs[2:]
            mkt = "SH" if rs.startswith("sh") else "SZ"
            ts = sym + "." + mkt
            result[ts] = {
                "name": parts[0],
                "price": sf(parts[3]),
                "open": sf(parts[1]),
                "close": sf(parts[3]),
                "high": sf(parts[4]),
                "low": sf(parts[5]),
                "volume": si(parts[8]),
                "amount": sf(parts[9]),
                "pct": sf(parts[32]) if len(parts) > 32 else 0.0,
            }
        except:
            continue
    return result

# ===== 获取股票列表 =====
def fetch_stock_list():
    print("  [主] 从东方财富获取股票列表...")
    url = ("https://push2.eastmoney.com/api/qt/clist/get"
           "?pn=1&pz=20&po=1&np=1&fltt=2&invt=2"
           "&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
           "&fields=f12,f14&cb=jQuery")
    txt = http_get(url)
    if not txt:
        print("  [备] 东方财富失败，尝试新浪...")
        return fetch_sina_list()
    try:
        s = txt.strip()
        if s.startswith("jQuery"):
            s = s[s.index("(") + 1:s.rindex(")")]
        j = json.loads(s)
        total = j.get("data", {}).get("total", 0)
        print(f"  总数: {total}")
    except:
        total = 0

    records = []
    for page in range(1, 600):
        p_url = (f"https://push2.eastmoney.com/api/qt/clist/get"
                 f"?pn={page}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3"
                 f"&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
                 f"&fields=f12,f14")
        ptxt = http_get(p_url)
        if not ptxt:
            break
        try:
            if ptxt.startswith("jQuery"):
                ptxt = ptxt[ptxt.index("(") + 1:ptxt.rindex(")")]
            pj = json.loads(ptxt)
            stocks = pj.get("data", {}).get("diff", []) or []
        except:
            break
        if not stocks:
            break
        for s in stocks:
            sym = str(s.get("f12", "")).zfill(6)
            name = s.get("f14", "")
            if not sym or not name:
                continue
            if sym.startswith("688"):
                ts = sym + ".SH"
            elif sym.startswith("60"):
                ts = sym + ".SH"
            else:
                ts = sym + ".SZ"
            records.append({"ts_code": ts, "symbol": sym, "name": name})
        if len(stocks) < 100:
            break
        time.sleep(0.5)
    print(f"  获取到 {len(records)} 只")
    return records

def fetch_sina_list():
    print("  [备] 从新浪获取股票列表...")
    url = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php"
           "/Market_Center.getHQNodeData?page=1&num=500&sort=symbol&asc=1&node=hs_a&_s_r_a=page")
    txt = http_get(url, headers={"Referer": "https://finance.sina.com.cn"})
    if not txt:
        return []
    try:
        j = json.loads(txt)
    except:
        return []
    records = []
    for item in j:
        sym = str(item.get("symbol", "")).strip()
        name = str(item.get("name", "")).strip()
        if not sym or not name:
            continue
        if sym.startswith("sh"):
            ts = sym[2:] + ".SH"
        elif sym.startswith("sz"):
            ts = sym[2:] + ".SZ"
        else:
            continue
        records.append({"ts_code": ts, "symbol": ts.split(".")[0], "name": name})
    print(f"  获取到 {len(records)} 只（新浪）")
    return records

# ===== 保存基础信息 =====
def save_basic(conn, stocks):
    sql = ("INSERT INTO stock_basic (ts_code, symbol, name, is_active) "
           "VALUES (%s, %s, %s, 1) "
           "ON DUPLICATE KEY UPDATE name=VALUES(name), updated_at=NOW()")
    ok = 0
    for s in stocks:
        if upsert(conn, sql, (s["ts_code"], s["symbol"], s["name"])):
            ok += 1
    print(f"  基础信息完成 ({ok}/{len(stocks)})")
    return ok

# ===== 保存每日K线 =====
def save_daily(conn, ts_code, klines):
    if not klines:
        return 0
    closes_for_ma = []
    records = 0
    for raw in klines:
        try:
            td = datetime.datetime.strptime(raw["date"], "%Y-%m-%d").date()
        except:
            continue
        close = raw.get("close")
        if close is None:
            continue
        closes_for_ma.append(close)
        n = len(closes_for_ma)

        ma5  = round(sum(closes_for_ma[-5:]) / min(5, n), 2)  if n >= 5  else None
        ma10 = round(sum(closes_for_ma[-10:]) / min(10, n), 2) if n >= 10 else None
        ma20 = round(sum(closes_for_ma[-20:]) / min(20, n), 2) if n >= 20 else None
        ma60 = round(sum(closes_for_ma[-60:]) / min(60, n), 2) if n >= 60 else None
        ma120 = ma60
        ma250 = ma60

        lb = closes_for_ma[-20:-1] if len(closes_for_ma) > 1 else closes_for_ma[-20:]
        s1 = round(min(lb) * 0.98, 2) if lb else None
        s2 = round(min(lb) * 0.95, 2) if lb else None
        s3 = round(min(lb) * 0.92, 2) if lb else None
        p1 = round(max(lb) * 1.02, 2) if lb else None
        p2 = round(max(lb) * 1.05, 2) if lb else None
        p3 = round(max(lb) * 1.08, 2) if lb else None

        pct = raw.get("pct") or 0
        rd = 1 if pct > 0 else 0
        fd = 1 if pct < 0 else 0
        rtp = pct if pct > 0 else 0.0
        fdp = pct if pct < 0 else 0.0
        b5  = 1 if (ma5  and close < ma5)  else 0
        b10 = 1 if (ma10 and close < ma10) else 0
        b20 = 1 if (ma20 and close < ma20) else 0
        b60 = 1 if (ma60 and close < ma60) else 0
        bs1 = 1 if (s1  and close < s1)  else 0
        bp1 = 1 if (p1  and close > p1)  else 0

        sql = ("INSERT INTO stock_daily_price (ts_code,trade_date,open,close,high,low,volume,amount,pct_change,"
               "rise_days,fall_days,rise_total_pct,fall_total_pct,"
               "ma5,ma10,ma20,ma60,ma120,ma250,"
               "support_1,support_2,support_3,pressure_1,pressure_2,pressure_3,"
               "break_ma5,break_ma10,break_ma20,break_ma60,break_support1,break_pressure1 "
               ") VALUES ("
               "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
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
               "updated_at=NOW()")

        vals = (ts_code, td, raw.get("open"), close, raw.get("high"), raw.get("low"),
                raw.get("volume"), raw.get("amount"), pct,
                rd, fd, rtp, fdp,
                ma5, ma10, ma20, ma60, ma120, ma250,
                s1, s2, s3, p1, p2, p3,
                b5, b10, b20, b60, bs1, bp1)

        if upsert(conn, sql, vals):
            records += 1
    return records

# ===== 主入口 =====
def main():
    print("=" * 55)
    print("  A股数据采集 v3（主备数据源）")
    print("=" * 55)
    conn = get_db()
    state = load_state()
    args = sys.argv[1:]

    # 仅基础信息
    if "--basic" in args:
        stocks = fetch_stock_list()
        save_basic(conn, stocks)
        state["basic_done"] = True
        save_state(state)
        conn.close()
        print("\n  完成！")
        return

    # 未采集过基础信息则先采集
    if not state.get("basic_done"):
        stocks = fetch_stock_list()
        save_basic(conn, stocks)
        state["basic_done"] = True
        save_state(state)
    else:
        cur = conn.cursor()
        cur.execute("SELECT ts_code, symbol, name FROM stock_basic WHERE is_active=1")
        stocks = [{"ts_code": r[0], "symbol": r[1], "name": r[2]} for r in cur.fetchall()]
        cur.close()
        print(f"\n  从DB加载 {len(stocks)} 只股票")

    start_idx = state.get("idx", 0) if "--resume" in args else 0
    days = 5 if "--daily" in args else 60
    print(f"\n  采集每日行情（最近{days}天），从第{start_idx + 1}只开始")

    ok_count = 0
    fail_count = 0
    fail_list = []

    for i, stk in enumerate(stocks[start_idx:], start=start_idx):
        ts = stk["ts_code"]
        name = stk["name"]
        print(f"\n  [{i+1}/{len(stocks)}] {ts} {name}...", end=" ", flush=True)

        # 主源
        klines = em_kline(ts, days=days)
        if not klines:
            print("(EM空→切换Sina) ", end="", flush=True)
            klines = sina_kline(ts, days=days)

        if not klines:
            print("⚠ 无数据")
            fail_count += 1
            fail_list.append(ts)
        else:
            n = save_daily(conn, ts, klines)
            print(f"✅ {n}条")
            ok_count += 1

        state["idx"] = i
        save_state(state)
        time.sleep(GAP)

    conn.close()
    print(f"\n  完成！成功 {ok_count} 只，失败 {fail_count} 只")
    if fail_list:
        print(f"  失败列表: {', '.join(fail_list[:10])}")

if __name__ == "__main__":
    main()
