#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导入上证/深证指数历史数据"""
import os, sys, time, json, datetime, warnings, mysql.connector
import urllib.request
warnings.filterwarnings("ignore")

DB_CONFIG = {
    "host": "localhost", "user": "root",
    "password": "OpenClaw@2026", "database": "a_stock_data"
}

INDICES = [
    {"ts_code": "000001.SH", "symbol": "000001", "name": "上证指数", "secid": "1.000001"},
    {"ts_code": "399001.SZ", "symbol": "399001", "name": "深证成指", "secid": "0.399001"},
    {"ts_code": "000300.SH", "symbol": "000300", "name": "沪深300", "secid": "1.000300"},
    {"ts_code": "000016.SH", "symbol": "000016", "name": "上证50", "secid": "1.000016"},
    {"ts_code": "399006.SZ", "symbol": "399006", "name": "创业板指", "secid": "0.399006"},
]

def http_get(url, timeout=15):
    h = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn",
    }
    req = urllib.request.Request(url, headers=h)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
            else:
                return None
    return None

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

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def sina_kline(ts_code, days=300):
    """通过新浪财经API获取K线"""
    sym, mkt = ts_code.split(".")
    sym2 = ("sh" if mkt == "SH" else "sz") + sym
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
                "date": item.get("day", ""),
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

def upsert(conn, sql, vals):
    c = conn.cursor()
    try:
        c.execute(sql, vals)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"    DB错误: {e}")
        return False
    finally:
        c.close()

def ensure_basic(conn, idx):
    sql = """INSERT INTO stock_basic (ts_code, symbol, name, industry, market, is_active)
             VALUES (%s, %s, %s, %s, %s, 1)
             ON DUPLICATE KEY UPDATE name=VALUES(name), is_active=1"""
    c = conn.cursor()
    c.execute(sql, (idx["ts_code"], idx["symbol"], idx["name"], "指数", "其他"))
    conn.commit()
    c.close()

def save_klines(conn, ts_code, klines):
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
        ma5  = round(sum(closes[-5:]) / min(5, n), 2) if n >= 5 else None
        ma10 = round(sum(closes[-10:]) / min(10, n), 2) if n >= 10 else None
        ma20 = round(sum(closes[-20:]) / min(20, n), 2) if n >= 20 else None
        ma60 = round(sum(closes[-60:]) / min(60, n), 2) if n >= 60 else None
        ma120 = round(sum(closes[-120:]) / min(120, n), 2) if n >= 120 else None
        ma250 = round(sum(closes[-250:]) / min(250, n), 2) if n >= 250 else None
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
                rd, fd, rtp, fdp, ma5, ma10, ma20, ma60, ma120, ma250,
                s1, s2, s3, p1, p2, p3, b5, b10, b20, b60, bs1, bp1)
        if upsert(conn, sql, vals):
            records += 1
    return records

def main():
    print("=" * 50)
    print("  📊 指数历史数据导入")
    print("=" * 50)
    conn = get_db()
    total = 0
    for idx in INDICES:
        print(f"\n▶ {idx['name']} ({idx['ts_code']})")
        ensure_basic(conn, idx)
        klines = sina_kline(idx["ts_code"], days=300)
        if not klines:
            print(f"  ⚠ 无数据，跳过")
            continue
        print(f"  获取到 {len(klines)} 条K线，写入中...")
        n = save_klines(conn, idx["ts_code"], klines)
        print(f"  ✅ 写入 {n} 条")
        total += n
        time.sleep(0.5)
    conn.close()
    print(f"\n🎉 完成！共写入 {total} 条行情数据")

if __name__ == "__main__":
    main()
