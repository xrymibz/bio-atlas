#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股历史数据快速后端填充 v2
- 16线程并发，每线程0.15秒间隔
- 约3-5分钟完成全量
- 断点续传
"""
import os, sys, time, json, datetime, warnings, mysql.connector
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
warnings.filterwarnings("ignore")

DB_CONFIG = {
    "host": "localhost", "user": "root",
    "password": "OpenClaw@2026", "database": "a_stock_data"
}
STATE_FILE = "/root/.openclaw/workspace/backfill_state.json"
WORKERS = 16   # 并发线程
GAP = 0.12     # 每线程请求间隔（秒）
DAYS = 300     # 历史天数

def http_get(url, enc="utf-8", timeout=10):
    h = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn",
    }
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode(enc, errors="ignore")
    except:
        return None

def sf(v):
    try:
        f = float(v) if v and str(v).strip() not in ("","nan","None") else None
        return round(f, 4) if f is not None else None
    except:
        return None

def si(v):
    try:
        return int(float(v)) if v and str(v).strip() not in ("","nan","None") else None
    except:
        return None

def ts_to_sina(ts):
    sym, mkt = ts.split(".")
    return ("sh" if mkt == "SH" else "sz") + sym

def fetch_klines(ts_code, days=DAYS):
    """获取单只股票历史K线"""
    sym2 = ts_to_sina(ts_code)
    url = (f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php"
           f"/CN_MarketData.getKLineData?symbol={sym2}&scale=240&ma=5&datalen={days}")
    txt = http_get(url)
    if not txt:
        return []
    try:
        data = json.loads(txt)
    except:
        return []
    klines = []
    for item in (data or []):
        try:
            open_p = sf(item.get("open"))
        close_p = sf(item.get("close"))
        pct_val = 0.0
        if open_p and open_p != 0 and close_p:
            pct_val = round((close_p - open_p) / open_p * 100, 4)
        klines.append({
                "date": item.get("day",""),
                "open": open_p,
                "close": close_p,
                "high": sf(item.get("high")),
                "low": sf(item.get("low")),
                "volume": si(item.get("volume")),
                "amount": sf(item.get("ma_price5")),
                "pct": pct_val,
            })
        except:
            continue
    return klines

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def upsert(conn, sql, vals):
    c = conn.cursor()
    try:
        c.execute(sql, vals)
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        c.close()

def save_klines(conn, ts_code, klines):
    """写入单只股票K线"""
    if not klines:
        return 0
    sql = ("INSERT INTO stock_daily_price "
           "(ts_code,trade_date,open,close,high,low,volume,amount,pct_change,"
           "rise_days,fall_days,rise_total_pct,fall_total_pct,"
           "ma5,ma10,ma20,ma60,ma120,ma250,"
           "support_1,support_2,support_3,pressure_1,pressure_2,pressure_3,"
           "break_ma5,break_ma10,break_ma20,break_ma60,break_support1,break_pressure1) "
           "VALUES ("
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
    records = 0
    closes = []
    for raw in klines:
        try:
            td = datetime.datetime.strptime(raw["date"], "%Y-%m-%d").date()
        except:
            continue
        close = raw.get("close")
        if close is None:
            continue
        closes.append(close)
        n = len(closes)
        ma5  = round(sum(closes[-5:]) / min(5, n), 2)  if n >= 5  else None
        ma10 = round(sum(closes[-10:]) / min(10, n), 2) if n >= 10 else None
        ma20 = round(sum(closes[-20:]) / min(20, n), 2) if n >= 20 else None
        ma60 = round(sum(closes[-60:]) / min(60, n), 2) if n >= 60 else None
        lb = closes[-20:-1] if len(closes) > 1 else closes[-20:]
        s1 = round(min(lb) * 0.98, 2) if lb else None
        s2 = round(min(lb) * 0.95, 2) if lb else None
        s3 = round(min(lb) * 0.92, 2) if lb else None
        p1 = round(max(lb) * 1.02, 2) if lb else None
        p2 = round(max(lb) * 1.05, 2) if lb else None
        p3 = round(max(lb) * 1.08, 2) if lb else None
        pct = raw.get("pct") or 0.0
        rd = 1 if pct > 0 else 0
        fd = 1 if pct < 0 else 0
        rtp = pct if pct > 0 else 0.0
        fdp = pct if pct < 0 else 0.0
        b5  = 1 if (ma5  and close < ma5)  else 0
        b10 = 1 if (ma10 and close < ma10) else 0
        b20 = 1 if (ma20 and close < ma20) else 0
        b60 = 1 if (ma60 and close < ma60) else 0
        bs1 = 1 if (s1 and close < s1) else 0
        bp1 = 1 if (p1 and close > p1) else 0
        vals = (ts_code, td, raw.get("open"), close, raw.get("high"), raw.get("low"),
                raw.get("volume"), raw.get("amount"), pct,
                rd, fd, rtp, fdp, ma5, ma10, ma20, ma60, ma60, ma60,
                s1, s2, s3, p1, p2, p3, b5, b10, b20, b60, bs1, bp1)
        if upsert(conn, sql, vals):
            records += 1
    return records

def process_one(stk):
    """线程处理单只股票"""
    ts = stk["ts_code"]
    klines = fetch_klines(ts, days=DAYS)
    if not klines:
        return ts, 0
    conn = get_db()
    n = save_klines(conn, ts, klines)
    conn.close()
    return ts, n

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE))
        except:
            pass
    return {"idx": 0, "done": [], "ok": 0, "fail": 0}

def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f)

def main():
    print("=" * 55)
    print("  🚀 A股快速后端填充 v2（16线程并发）")
    print("=" * 55)

    state = load_state()
    start_idx = state.get("idx", 0)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT ts_code, symbol, name FROM stock_basic WHERE is_active=1")
    stocks = [{"ts_code": r[0], "symbol": r[1], "name": r[2]} for r in cur.fetchall()]
    cur.close()
    conn.close()

    remaining = stocks[start_idx:]
    print(f"共 {len(stocks)} 只股票，待处理 {len(remaining)} 只")
    print(f"并发 {WORKERS} 线程，间隔 {GAP}s")

    ok_total = state.get("ok", 0)
    fail_total = state.get("fail", 0)
    done_set = set(state.get("done", []))

    t0 = time.time()
    processed = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        # 分批提交，每批稍作延迟控制总QPS
        batch_size = WORKERS * 2
        for batch_start in range(0, len(remaining), batch_size):
            batch = remaining[batch_start:batch_start + batch_size]
            futures = {executor.submit(process_one, s): s for s in batch}

            for future in as_completed(futures):
                ts, n = future.result()
                processed += 1
                if n > 0:
                    ok_total += 1
                    done_set.add(ts)
                    print(f"\r  [{processed}/{len(remaining)}] {ts} ✅ {n}条 ({time.time()-t0:.0f}s)", end="", flush=True)
                else:
                    fail_total += 1
                    print(f"\r  [{processed}/{len(remaining)}] {ts} ⚠ 无数据", end="", flush=True)

                # 每10只保存一次状态
                if processed % 10 == 0:
                    state["idx"] = start_idx + processed
                    state["ok"] = ok_total
                    state["fail"] = fail_total
                    state["done"] = list(done_set)
                    save_state(state)

                time.sleep(GAP)  # 控制频率

    # 最终状态
    state["idx"] = start_idx + len(remaining)
    state["ok"] = ok_total
    state["fail"] = fail_total
    state["done"] = list(done_set)
    save_state(state)

    elapsed = time.time() - t0
    print(f"\n\n🎉 完成！{ok_total}只股票写入成功，{fail_total}只失败")
    print(f"耗时: {elapsed:.0f}秒 ({elapsed/60:.1f}分钟)")

if __name__ == "__main__":
    main()
