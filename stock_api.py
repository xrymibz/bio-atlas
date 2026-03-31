#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股数据 API 服务（Flask）
端口：5003
12个核心接口，全部返回 JSON
import re
启动：python3 stock_api.py
"""

import os, sys, math, datetime, time, json
from functools import wraps
from flask import Flask, jsonify, request

# ===================== 配置 =====================
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "OpenClaw@2026",
    "database": "a_stock_data",
    "charset": "utf8mb4",
    "autocommit": True
}

# ===================== 统一响应格式 =====================
def api_ok(data=None, msg="success"):
    return jsonify({"code": 0, "msg": msg, "data": data})

def api_err(msg="error", code=1, data=None):
    return jsonify({"code": code, "msg": msg, "data": data})

def param_required(*names):
    def deco(f):
        @wraps(f)
        def fn(*args, **kwargs):
            missing = [n for n in names if not request.args.get(n)]
            if missing:
                return api_err(f"缺少参数: {', '.join(missing)}", code=400)
            return f(*args, **kwargs)
        return fn
    return deco

# ===================== DB工具 =====================
import mysql.connector
from mysql.connector import pooling

cnx_pool = pooling.MySQLConnectionPool(
    pool_name="astock", pool_size=32, pool_reset_session=True, **DB_CONFIG
)

def get_db():
    return cnx_pool.get_connection()

def sf(v):
    try:
        f = float(v) if v is not None and str(v).strip() not in ("", "nan", "None") else None
        return round(f, 4) if f is not None else None
    except:
        return None

def si(v):
    try:
        return int(float(v)) if v is not None and str(v).strip() not in ("", "nan", "None") else None
    except:
        return None

def rows(sql, args=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, args or ())
    result = cur.fetchall()
    cur.close()
    conn.close()
    return result

def row(sql, args=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, args or ())
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result

# ===================== 辅助计算 =====================

def calc_rsi(closes, period=14):
    """计算RSI"""
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 4)

def calc_macd(closes, fast=12, slow=26, signal=9):
    """计算MACD (dif, dea, macd)"""
    if len(closes) < slow + signal:
        return None, None, None

    def ema(data, n):
        if len(data) < n:
            return None
        k = 2.0 / (n + 1)
        ema_val = sum(data[:n]) / n
        for v in data[n:]:
            ema_val = v * k + ema_val * (1 - k)
        return ema_val

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    if ema_fast is None or ema_slow is None:
        return None, None, None

    dif = round(ema_fast - ema_slow, 4)

    # DEA = EMA(DIF, 9)
    dif_series = []
    for i in range(slow - 1, len(closes)):
        ef = ema(closes[:i+1], fast)
        es = ema(closes[:i+1], slow)
        if ef and es:
            dif_series.append(ef - es)
    dea = ema(dif_series, signal) if len(dif_series) >= signal else None
    macd = round((dif - dea) * 2, 4) if dif and dea else None

    return dif, (round(dea, 4) if dea else None), macd

def calc_kdj(highs, lows, closes, n=9, m1=3, m2=3):
    """计算KDJ"""
    if len(closes) < n:
        return None, None, None
    rsvs = []
    for i in range(n - 1, len(closes)):
        h = max(highs[i - n + 1:i + 1])
        l = min(lows[i - n + 1:i + 1])
        c = closes[i]
        if h == l:
            rsvs.append(50)
        else:
            rsvs.append((c - l) / (h - l) * 100)
    k = 50.0
    d = 50.0
    for r in rsvs:
        k = (2 * k + r) / 3
        d = (2 * d + k) / 3
    j = 3 * k - 2 * d
    return round(k, 4), round(d, 4), round(j, 4)

def calc_boll(closes, n=20, k=2):
    """计算布林带"""
    if len(closes) < n:
        return None, None, None
    ma = sum(closes[-n:]) / n
    std = math.sqrt(sum((x - ma) ** 2 for x in closes[-n:]) / n)
    upper = round(ma + k * std, 3)
    mid = round(ma, 3)
    lower = round(ma - k * std, 3)
    return upper, mid, lower

def compute_indicators_from_kline(klines):
    """
    从K线数据计算技术指标
    klines: list of {open, close, high, low, volume, amount, pct_change}
    返回 dict
    """
    if not klines or len(klines) < 5:
        return {}

    closes = [k["close"] for k in klines if k.get("close") is not None]
    highs = [k["high"] for k in klines if k.get("high") is not None]
    lows = [k["low"] for k in klines if k.get("low") is not None]
    vols = [k["volume"] for k in klines if k.get("volume") is not None]

    n = len(closes)
    result = {}

    # 均线
    result["ma5"] = round(sum(closes[-5:]) / min(5, n), 3) if n >= 5 else None
    result["ma10"] = round(sum(closes[-10:]) / min(10, n), 3) if n >= 10 else None
    result["ma20"] = round(sum(closes[-20:]) / min(20, n), 3) if n >= 20 else None
    result["ma60"] = round(sum(closes[-60:]) / min(60, n), 3) if n >= 60 else None
    result["ma120"] = round(sum(closes[-120:]) / min(120, n), 3) if n >= 120 else None
    result["ma250"] = round(sum(closes[-250:]) / min(250, n), 3) if n >= 250 else None

    # MACD
    dif, dea, macd = calc_macd(closes)
    result["dif"] = dif
    result["dea"] = dea
    result["macd"] = macd

    # RSI
    result["rsi_6"] = calc_rsi(closes, 6)
    result["rsi_12"] = calc_rsi(closes, 12)
    result["rsi_24"] = calc_rsi(closes, 24)

    # BOLL
    boll_upper, boll_mid, boll_lower = calc_boll(closes)
    result["boll_upper"] = boll_upper
    result["boll_mid"] = boll_mid
    result["boll_lower"] = boll_lower

    # KDJ
    if len(highs) >= 9 and len(lows) >= 9 and len(closes) >= 9:
        k, d, j = calc_kdj(highs, lows, closes)
        result["kdj_k"] = k
        result["kdj_d"] = d
        result["kdj_j"] = j
    else:
        result["kdj_k"] = result["kdj_d"] = result["kdj_j"] = None

    # 振幅
    if len(klines) >= 2 and highs and lows:
        prev_close = klines[-2].get("close")
        if prev_close:
            result["swing"] = round((max(highs) - min(lows)) / prev_close * 100, 4)

    # 量比（今日成交量/前5日均量）
    if vols and len(vols) >= 6:
        avg_vol5 = sum(vols[-6:-1]) / 5
        today_vol = vols[-1]
        result["volume_ratio"] = round(today_vol / avg_vol5, 4) if avg_vol5 else None

    # 换手率（用成交量/流通股本估算，简化处理）
    if vols and len(vols) >= 5:
        result["turnover_rate"] = round(sum(vols[-5:]) / 5 / 1000000, 4)  # 简化估算

    return result

def score_to_level(score):
    if score >= 80: return "强烈推荐"
    if score >= 65: return "值得关注"
    if score >= 50: return "中性"
    if score >= 35: return "谨慎"
    return "回避"

# ===================== 接口1：股票基础信息 =====================
@app.route("/api/stock/info")
@param_required("ts_code")
def stock_info():
    ts_code = request.args.get("ts_code", "").strip()

    sql = """
    SELECT ts_code, symbol, name, industry, sub_industry, market,
           list_date, is_active, created_at, updated_at
    FROM stock_basic
    WHERE ts_code = %s
    """
    r = row(sql, (ts_code,))
    if not r:
        return api_err("股票不存在", code=404)

    fields = ["ts_code", "symbol", "name", "industry", "sub_industry", "market",
               "list_date", "is_active", "created_at", "updated_at"]
    data = {f: (str(v) if v is not None else None) for f, v in zip(fields, r)}

    # 补充最新行情（优先实时价格，失败则用数据库缓存）
    latest = row("""
        SELECT close, pct_change, volume, trade_date
        FROM stock_daily_price
        WHERE ts_code = %s ORDER BY trade_date DESC LIMIT 1
    """, (ts_code,))

    # 新浪实时行情接口
    mkt_sina = "sz" if ts_code.endswith(".SZ") else "sh"
    sym = ts_code.split(".")[0]
    sina_url = f"https://hq.sinajs.cn/list={mkt_sina}{sym}"
    rt_price = None; rt_pct = None; rt_time = None
    try:
        import urllib.request
        req = urllib.request.Request(sina_url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn"
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("gbk", errors="ignore")
        import re
        m = re.search('="([^"]+)"', raw)
        if m:
            fields = m.group(1).split(",")
            # 格式: 名称(0),开盘价(1),昨收(2),当前价(3),最高(4),最低(5),...量(8),额(9),时间(30/31)
            if len(fields) > 8 and fields[3] and fields[3] != "0":
                rt_price = sf(fields[3])
                rt_yest_close = sf(fields[2])
                if rt_price and rt_yest_close:
                    rt_pct = round((rt_price - rt_yest_close) / rt_yest_close * 100, 2)
                # 取时间
                if len(fields) > 31 and fields[31]:
                    rt_time = f"{fields[30]} {fields[31]}" if fields[30] else None
                elif len(fields) > 30 and fields[30]:
                    rt_time = fields[30]
    except Exception:
        pass

    if rt_price:
        data["latest_price"] = rt_price
        data["pct_change"] = rt_pct
        data["latest_date"] = rt_time or "实时"
    else:
        data["latest_price"] = sf(latest[0]) if latest else None
        data["pct_change"] = sf(latest[1]) if latest else None
        data["latest_date"] = str(latest[3]) if latest and latest[3] else None

    if latest:
        data["volume"] = si(latest[2])

    return api_ok(data)

# ===================== 接口2：日线行情 =====================
@app.route("/api/stock/daily")
@param_required("ts_code")
def stock_daily():
    ts_code = request.args.get("ts_code", "").strip()
    days = min(int(request.args.get("days", 60)), 500)
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(int(request.args.get("page_size", 100)), 500)
    offset = (page - 1) * page_size

    # 总数
    total_row = row("SELECT COUNT(*) FROM stock_daily_price WHERE ts_code=%s", (ts_code,))
    total = total_row[0] if total_row else 0

    sql = """
    SELECT trade_date, open, close, high, low, volume, amount, pct_change,
           ma5, ma10, ma20, ma60, ma120, ma250,
           support_1, support_2, support_3, pressure_1, pressure_2, pressure_3,
           break_ma5, break_ma10, break_ma20, break_ma60,
           rise_days, fall_days, rise_total_pct, fall_total_pct
    FROM stock_daily_price
    WHERE ts_code = %s
    ORDER BY trade_date DESC
    LIMIT %s OFFSET %s
    """
    db_rows = rows(sql, (ts_code, page_size, offset))

    items = []
    for r in db_rows:
        items.append({
            "trade_date": str(r[0]) if r[0] else None,
            "open": sf(r[1]), "close": sf(r[2]), "high": sf(r[3]), "low": sf(r[4]),
            "volume": si(r[5]), "amount": sf(r[6]), "pct_change": sf(r[7]),
            "ma5": sf(r[8]), "ma10": sf(r[9]), "ma20": sf(r[10]),
            "ma60": sf(r[11]), "ma120": sf(r[12]), "ma250": sf(r[13]),
            "support_1": sf(r[14]), "support_2": sf(r[15]), "support_3": sf(r[16]),
            "pressure_1": sf(r[17]), "pressure_2": sf(r[18]), "pressure_3": sf(r[19]),
            "break_ma5": r[20], "break_ma10": r[21], "break_ma20": r[22], "break_ma60": r[23],
            "rise_days": r[24], "fall_days": r[25],
            "rise_total_pct": sf(r[26]), "fall_total_pct": sf(r[27]),
        })

    return api_ok({
        "ts_code": ts_code, "total": total,
        "page": page, "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 1,
        "items": items
    })

# ===================== 接口3：技术指标 =====================
@app.route("/api/stock/indicator")
@param_required("ts_code")
def stock_indicator():
    ts_code = request.args.get("ts_code", "").strip()
    days = min(int(request.args.get("days", 60)), 500)

    # 先从 stock_daily_indicator 查
    ind_rows = rows("""
        SELECT trade_date, ma5, ma10, ma20, ma60, ma120, ma250,
               dif, dea, macd, rsi_6, rsi_12, rsi_24,
               boll_upper, boll_mid, boll_lower,
               kdj_k, kdj_d, kdj_j,
               swing, turnover_rate, volume_ratio
        FROM stock_daily_indicator
        WHERE ts_code = %s
        ORDER BY trade_date DESC LIMIT %s
    """, (ts_code, days))

    if ind_rows:
        items = []
        for r in ind_rows:
            items.append({
                "trade_date": str(r[0]) if r[0] else None,
                "ma5": sf(r[1]), "ma10": sf(r[2]), "ma20": sf(r[3]), "ma60": sf(r[4]),
                "ma120": sf(r[5]), "ma250": sf(r[6]),
                "dif": sf(r[7]), "dea": sf(r[8]), "macd": sf(r[9]),
                "rsi_6": sf(r[10]), "rsi_12": sf(r[11]), "rsi_24": sf(r[12]),
                "boll_upper": sf(r[13]), "boll_mid": sf(r[14]), "boll_lower": sf(r[15]),
                "kdj_k": sf(r[16]), "kdj_d": sf(r[17]), "kdj_j": sf(r[18]),
                "swing": sf(r[19]), "turnover_rate": sf(r[20]), "volume_ratio": sf(r[21]),
            })
        return api_ok({"source": "indicator_table", "items": items})

    # 如果 indicator 表空，从 price 数据实时计算（至少取300条保证MA计算）
    price_rows = rows("""
        SELECT trade_date, open, close, high, low, volume, amount, pct_change
        FROM stock_daily_price
        WHERE ts_code = %s
        ORDER BY trade_date DESC LIMIT %s
    """, (ts_code, max(min(days, 250), 300)))

    if not price_rows:
        return api_err("无行情数据", code=404)

    # 逆序为升序（计算指标需要从旧到新）
    price_rows = list(reversed(price_rows))
    # Sina格式: open=昨收, close=今收, pct_change=0
    # 用(open,close)反推真实涨跌幅
    klines = []
    for i, r in enumerate(price_rows):
        open_p = sf(r[1]); close_p = sf(r[2])
        pct_c = 0.0
        if open_p and open_p != 0 and close_p:
            pct_c = round((close_p - open_p) / open_p * 100, 4)
        klines.append({
            "open": open_p, "close": close_p, "high": sf(r[3]),
            "low": sf(r[4]), "volume": si(r[5]), "amount": sf(r[6]),
            "pct_change": pct_c, "trade_date": str(r[0]) if r[0] else None
        })

    # 从第20天开始计算指标（需要至少20日数据）
    items = []
    for i in range(20, len(klines) + 1):
        subset = klines[:i]
        ind = compute_indicators_from_kline(subset)
        if ind:
            ind["trade_date"] = klines[i - 1]["trade_date"]
            ind["close"] = klines[i - 1].get("close")
            ind["open"] = klines[i - 1].get("open")
            ind["volume"] = klines[i - 1].get("volume")
            items.append(ind)

    items.reverse()  # 回到降序（最新在前）
    return api_ok({"source": "computed", "items": items[-days:]})

# ===================== 接口4：资金数据 =====================
@app.route("/api/stock/capital")
@param_required("ts_code")
def stock_capital():
    ts_code = request.args.get("ts_code", "").strip()
    days = min(int(request.args.get("days", 30)), 500)

    sql = """
    SELECT trade_date, main_inflow, super_inflow, big_inflow,
           mid_inflow, small_inflow, north_money, north_hold,
           margin, margin_change
    FROM stock_daily_capital
    WHERE ts_code = %s
    ORDER BY trade_date DESC LIMIT %s
    """
    db_rows = rows(sql, (ts_code, days))

    if not db_rows:
        return api_ok({"source": "table", "items": [], "note": "资金数据需从东方财富收费接口获取，免费数据源暂无此字段"})

    items = []
    for r in db_rows:
        items.append({
            "trade_date": str(r[0]) if r[0] else None,
            "main_inflow": sf(r[1]), "super_inflow": sf(r[2]), "big_inflow": sf(r[3]),
            "mid_inflow": sf(r[4]), "small_inflow": sf(r[5]),
            "north_money": sf(r[6]), "north_hold": sf(r[7]),
            "margin": sf(r[8]), "margin_change": sf(r[9]),
        })
    return api_ok({"source": "table", "items": items})

# ===================== 接口5：筹码分布 =====================
@app.route("/api/stock/chip")
@param_required("ts_code")
def stock_chip():
    ts_code = request.args.get("ts_code", "").strip()
    days = min(int(request.args.get("days", 30)), 500)

    sql = """
    SELECT trade_date, avg_cost, concentration,
           chip_70_low, chip_70_up, chip_90_low, chip_90_up, profit_ratio
    FROM stock_chip_distribution
    WHERE ts_code = %s
    ORDER BY trade_date DESC LIMIT %s
    """
    db_rows = rows(sql, (ts_code, days))

    if not db_rows:
        # 尝试从每日价格数据估算筹码
        price_rows = rows("""
            SELECT trade_date, close, volume FROM stock_daily_price
            WHERE ts_code = %s ORDER BY trade_date DESC LIMIT %s
        """, (ts_code, min(days, 30)))
        if price_rows:
            items = []
            for r in price_rows:
                close = sf(r[1])
                vol = si(r[2])
                if close and vol:
                    items.append({
                        "trade_date": str(r[0]) if r[0] else None,
                        "avg_cost": round(close * 0.95, 2),  # 估算
                        "concentration": round(vol / 10000000, 4) if vol else None,
                        "chip_70_low": round(close * 0.92, 2),
                        "chip_70_up": round(close * 1.08, 2),
                        "chip_90_low": round(close * 0.88, 2),
                        "chip_90_up": round(close * 1.12, 2),
                        "profit_ratio": round((close - close * 0.95) / close * 100, 2),
                        "_note": "（估算值，基于价格模型）"
                    })
            return api_ok({"source": "estimated", "items": items})

        return api_err("无筹码数据", code=404)

    items = []
    for r in db_rows:
        items.append({
            "trade_date": str(r[0]) if r[0] else None,
            "avg_cost": sf(r[1]), "concentration": sf(r[2]),
            "chip_70_low": sf(r[3]), "chip_70_up": sf(r[4]),
            "chip_90_low": sf(r[5]), "chip_90_up": sf(r[6]),
            "profit_ratio": sf(r[7]),
        })
    return api_ok({"source": "table", "items": items})

# ===================== 接口6：每日事件 =====================
@app.route("/api/stock/events")
@param_required("ts_code")
def stock_events():
    ts_code = request.args.get("ts_code", "").strip()
    days = min(int(request.args.get("days", 30)), 500)

    sql = """
    SELECT trade_date, is_limit_up, is_limit_down, is_break_ma20, is_break_ma60,
           is_high_1y, is_low_1y, is_unlock_day, unlock_ratio
    FROM stock_daily_events
    WHERE ts_code = %s
    ORDER BY trade_date DESC LIMIT %s
    """
    db_rows = rows(sql, (ts_code, days))

    if not db_rows:
        # 从 price 数据计算事件
        price_rows = rows("""
            SELECT trade_date, open, close, ma20, ma60, volume
            FROM stock_daily_price
            WHERE ts_code = %s ORDER BY trade_date DESC LIMIT %s
        """, (ts_code, days))
        if price_rows:
            price_rows = list(reversed(price_rows))
            items = []
            for i, r in enumerate(price_rows):
                open_p = sf(r[1]); close = sf(r[2])
                pct = 0.0
                if open_p and open_p != 0 and close:
                    pct = round((close - open_p) / open_p * 100, 4)
                ma20 = sf(r[3]); ma60 = sf(r[4])
                prev_close = open_p

                item = {
                    "trade_date": str(r[0]) if r[0] else None,
                    "is_limit_up": 1 if pct and pct >= 9.9 else 0,
                    "is_limit_down": 1 if pct and pct <= -9.9 else 0,
                    "is_break_ma20": 1 if ma20 and close and close < ma20 else 0,
                    "is_break_ma60": 1 if ma60 and close and close < ma60 else 0,
                    "is_high_1y": 0, "is_low_1y": 0,
                    "is_unlock_day": 0, "unlock_ratio": None,
                }
                items.append(item)
            items.reverse()
            return api_ok({"source": "computed", "items": items[-days:]})

        return api_err("无事件数据", code=404)

    items = []
    for r in db_rows:
        items.append({
            "trade_date": str(r[0]) if r[0] else None,
            "is_limit_up": r[1], "is_limit_down": r[2],
            "is_break_ma20": r[3], "is_break_ma60": r[4],
            "is_high_1y": r[5], "is_low_1y": r[6],
            "is_unlock_day": r[7], "unlock_ratio": sf(r[8]),
        })
    return api_ok({"source": "table", "items": items})

# ===================== 接口7：基本面估值 =====================
@app.route("/api/stock/funda")
@param_required("ts_code")
def stock_funda():
    ts_code = request.args.get("ts_code", "").strip()
    days = min(int(request.args.get("days", 30)), 500)

    sql = """
    SELECT trade_date, pe_ttm, pb_mrq, ps_ttm, dividend_yield,
           total_share, float_share, market_cap, float_cap,
           holder_num, holder_change
    FROM stock_daily_funda
    WHERE ts_code = %s
    ORDER BY trade_date DESC LIMIT %s
    """
    db_rows = rows(sql, (ts_code, days))

    if not db_rows:
        # 从价格和基本信息估算
        latest_price_row = row("""
            SELECT MAX(close) FROM stock_daily_price WHERE ts_code=%s
        """, (ts_code,))
        price = sf(latest_price_row[0]) if latest_price_row else None

        if price:
            # 用简单估算填充（实际数据需收费接口）
            price_rows = rows("""
                SELECT trade_date, close FROM stock_daily_price
                WHERE ts_code=%s ORDER BY trade_date DESC LIMIT %s
            """, (ts_code, days))
            items = [{
                "trade_date": str(r[0]) if r[0] else None,
                "pe_ttm": None, "pb_mrq": None, "ps_ttm": None,
                "dividend_yield": None,
                "total_share": None, "float_share": None,
                "market_cap": round(price * 100000000, 2) if price else None,
                "float_cap": round(price * 80000000, 2) if price else None,
                "holder_num": None, "holder_change": None,
                "_note": "市值估算值（股本数据需收费接口）"
            } for r in price_rows]
            return api_ok({"source": "estimated", "items": items})

        return api_err("无基本面数据", code=404)

    items = []
    for r in db_rows:
        items.append({
            "trade_date": str(r[0]) if r[0] else None,
            "pe_ttm": sf(r[1]), "pb_mrq": sf(r[2]), "ps_ttm": sf(r[3]),
            "dividend_yield": sf(r[4]),
            "total_share": sf(r[5]), "float_share": sf(r[6]),
            "market_cap": sf(r[7]), "float_cap": sf(r[8]),
            "holder_num": si(r[9]), "holder_change": sf(r[10]),
        })
    return api_ok({"source": "table", "items": items})

# ===================== 接口8：市场概况 =====================
@app.route("/api/market/overview")
def market_overview():
    # 最新一条市场概况
    r = row("""
        SELECT trade_date, rise_count, fall_count, limit_up_count, limit_down_count,
               total_volume, total_amount, index_close, index_pct, earn_ratio
        FROM stock_market_overview
        ORDER BY trade_date DESC LIMIT 1
    """)
    if r:
        return api_ok({
            "source": "table",
            "data": {
                "trade_date": str(r[0]) if r[0] else None,
                "rise_count": si(r[1]), "fall_count": si(r[2]),
                "limit_up_count": si(r[3]), "limit_down_count": si(r[4]),
                "total_volume": sf(r[5]), "total_amount": sf(r[6]),
                "index_close": sf(r[7]), "index_pct": sf(r[8]),
                "earn_ratio": sf(r[9]),
            }
        })

    # 实时从全市场数据计算
    stats = row("""
        SELECT COUNT(DISTINCT ts_code) FROM stock_daily_price
        WHERE trade_date = (SELECT MAX(trade_date) FROM stock_daily_price)
    """)
    total = stats[0] if stats else 0

    day = row("SELECT trade_date FROM stock_daily_price ORDER BY trade_date DESC LIMIT 1")
    latest_date = str(day[0]) if day and day[0] else None

    rise_r = row("""
        SELECT COUNT(*) FROM stock_daily_price p
        JOIN stock_basic b ON b.ts_code = p.ts_code
        WHERE p.trade_date = %s AND b.is_active = 1
        AND (p.close - p.open) / p.open * 100 > 0
    """, (latest_date,))
    fall_r = row("""
        SELECT COUNT(*) FROM stock_daily_price p
        JOIN stock_basic b ON b.ts_code = p.ts_code
        WHERE p.trade_date = %s AND b.is_active = 1
        AND (p.close - p.open) / p.open * 100 < 0
    """, (latest_date,))
    limit_up_r = row("""
        SELECT COUNT(*) FROM stock_daily_price
        WHERE trade_date = %s AND (close - open) / open * 100 >= 9.9
    """, (latest_date,))
    limit_down_r = row("""
        SELECT COUNT(*) FROM stock_daily_price
        WHERE trade_date = %s AND (close - open) / open * 100 <= -9.9
    """, (latest_date,))
    vol_r = row("""
        SELECT SUM(volume), SUM(amount) FROM stock_daily_price
        WHERE trade_date = %s
    """, (latest_date,))
    idx_r = row("""
        SELECT close, pct_change FROM stock_daily_price
        WHERE ts_code = '000001.SH' ORDER BY trade_date DESC LIMIT 1
    """)

    rise_count = rise_r[0] if rise_r else 0
    fall_count = fall_r[0] if fall_r else 0
    earn_ratio = round(rise_count / (rise_count + fall_count) * 100, 2) if (rise_count + fall_count) > 0 else 0

    return api_ok({
        "source": "computed",
        "data": {
            "trade_date": latest_date,
            "rise_count": rise_count, "fall_count": fall_count,
            "limit_up_count": limit_up_r[0] if limit_up_r else 0,
            "limit_down_count": limit_down_r[0] if limit_down_r else 0,
            "total_volume": sf(vol_r[0]) if vol_r else None,
            "total_amount": sf(vol_r[1]) if vol_r else None,
            "index_close": sf(idx_r[0]) if idx_r else None,
            "index_pct": sf(idx_r[1]) if idx_r else None,
            "earn_ratio": earn_ratio,
            "total_stocks": total,
        }
    })

# ===================== 接口9：强势股池 =====================
@app.route("/api/strategy/pool")
def strategy_pool():
    """
    选股策略（简化版）：
    1. 收盘价 > ma20（站上20日线）
    2. 近5日累计涨幅 > 0
    3. 近5日均量 > 近20日均量（放量）
    4. 非ST
    5. 按综合评分排序
    """
    top_n = min(int(request.args.get("top", 30)), 5000)
    page = max(int(request.args.get("page", 1)), 1)
    page_size = top_n  # top_n控制每页返回条数

    # 取出最新日期
    latest_date_row = row("SELECT MAX(trade_date) FROM stock_daily_price")
    latest_date = latest_date_row[0] if latest_date_row else None
    if not latest_date:
        return api_err("无数据", code=404)

    # 取最新交易日所有股票基础数据
    # 直接读预计算字段，无任何子查询
    pool_rows = rows("""
        SELECT
            p.ts_code, b.name, b.industry,
            p.close, p.pct_change,
            p.ma5, p.ma10, p.ma20, p.ma60,
            p.volume,
            p.rise_days, p.fall_days,
            p.rise_5d, p.avg_vol_20, p.high_20d
        FROM stock_daily_price p
        JOIN stock_basic b ON b.ts_code = p.ts_code
        WHERE p.trade_date = %s
        AND b.is_active = 1
        AND b.name NOT LIKE '%%ST%%'
        AND b.name NOT LIKE '%%*%%'
    """, (latest_date,))

    items = []
    for r in pool_rows:
        ts = r[0]; name = r[1]; industry = r[2]
        close = sf(r[3]); pct = sf(r[4])
        ma5 = sf(r[5]); ma10 = sf(r[6]); ma20 = sf(r[7]); ma60 = sf(r[8])
        volume = si(r[9])
        rise_days = si(r[10]) or 0
        fall_days = si(r[11]) or 0
        rise_5d = sf(r[12]) or 0.0
        avg_vol_20 = sf(r[13]) or 0.0
        high_20d = sf(r[14])

        # 回撤：近20日高点到现价的跌幅
        drawdown = round((high_20d - close) / high_20d * 100, 2) if high_20d and high_20d > 0 else 0.0

        # 综合评分（满分100）
        score = 0.0
        above_ma = sum(10 for v in [ma5, ma10, ma20] if v is not None and close > v)
        score += above_ma
        score += min(25, max(0, rise_5d * 5))
        if avg_vol_20 > 0:
            score += min(20, (volume / avg_vol_20) * 10)
        if ma20:
            distance = (close - ma20) / ma20 * 100
            score += min(15, max(0, distance * 3))
        score += min(10, max(0, (pct or 0) * 2 + 5))

        # rise_streak类型：只保留站上ma20且近5日累计涨幅>0的（强势股逻辑）
        # 其他类型（fall_streak/drawdown/recent_rise）保留所有
        stype = request.args.get("type", "score")
        if stype == "rise_streak":
            if not close or not ma20 or rise_5d <= 0:
                continue

        items.append({
            "ts_code": ts, "name": name, "industry": industry or "未知",
            "close": close, "pct_change": pct,
            "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
            "rise_5d": rise_5d, "rise_5d_pct": rise_5d,
            "volume_ratio": round(volume / avg_vol_20, 2) if avg_vol_20 else None,
            "score": round(score, 1),
            "high_20d": high_20d,
            "drawdown": drawdown,
            "rise_days": rise_days,
            "fall_days": fall_days,
        })
    # 按type排序
    sort_type = request.args.get("type", "score")
    if sort_type == "rise_streak":
        items.sort(key=lambda x: (-x["rise_days"], -x["score"]))
    elif sort_type == "fall_streak":
        items.sort(key=lambda x: (-x["fall_days"], -x["score"]))
    elif sort_type == "drawdown":
        items.sort(key=lambda x: (-x["drawdown"], -x["score"]))
    elif sort_type == "recent_rise":
        items.sort(key=lambda x: (-x.get("rise_5d", 0), -x["score"]))
    else:
        items.sort(key=lambda x: -x["score"])
    total = len(items)

    # 分页
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]

    return api_ok({
        "total": total, "page": page, "page_size": page_size,
        "strategy": "站上20日线 + 近5日涨幅 + 放量",
        "items": page_items
    })


# ===================== 接口10：趋势与破位 =====================
@app.route("/api/strategy/trend")
@param_required("ts_code")
def strategy_trend():
    ts_code = request.args.get("ts_code", "").strip()
    days = int(request.args.get("days", 60))

    price_rows = rows("""
        SELECT trade_date, open, close, high, low, volume, amount, pct_change,
               ma5, ma10, ma20, ma60, ma120,
               support_1, pressure_1
        FROM stock_daily_price
        WHERE ts_code = %s
        ORDER BY trade_date DESC LIMIT %s
    """, (ts_code, days))

    if not price_rows or len(price_rows) < 20:
        return api_err("数据不足", code=404)

    latest = price_rows[0]
    close = sf(latest[4]); ma5 = sf(latest[8]); ma10 = sf(latest[9])
    ma20 = sf(latest[10]); ma60 = sf(latest[11]); ma120 = sf(latest[12])
    s1 = sf(latest[13]); p1 = sf(latest[14])

    # 趋势判断
    if ma20 and close > ma20 and ma60 and close > ma60 and ma120 and close > ma120:
        trend = "上升趋势"
        trend_level = "强"
    elif ma20 and close > ma20:
        trend = "震荡偏强"
        trend_level = "中"
    elif ma20 and close < ma20:
        trend = "下降趋势"
        trend_level = "弱"
    else:
        trend = "震荡"
        trend_level = "中"

    # 各周期位置
    position_ma5 = "上方" if (ma5 and close > ma5) else "下方"
    position_ma10 = "上方" if (ma10 and close > ma10) else "下方"
    position_ma20 = "上方" if (ma20 and close > ma20) else "下方"
    position_ma60 = "上方" if (ma60 and close > ma60) else "下方"

    # 破位信号
    break_signals = []
    if ma5 and close < ma5: break_signals.append("跌破MA5")
    if ma10 and close < ma10: break_signals.append("跌破MA10")
    if ma20 and close < ma20: break_signals.append("跌破MA20")
    if ma60 and close < ma60: break_signals.append("跌破MA60")
    if s1 and close < s1: break_signals.append("跌破支撑S1")

    # 突破信号
    break_up_signals = []
    if ma5 and close > ma5 and price_rows[1] and sf(price_rows[1][8]) and sf(price_rows[1][8]) <= ma5:
        break_up_signals.append("突破MA5")
    if ma20 and close > ma20 and price_rows[1] and sf(price_rows[1][10]) and sf(price_rows[1][10]) <= ma20:
        break_up_signals.append("突破MA20")
    if ma60 and close > ma60 and price_rows[1] and sf(price_rows[1][11]) and sf(price_rows[1][11]) <= ma60:
        break_up_signals.append("突破MA60")

    # 近10日高低点
    recent = price_rows[:min(10, len(price_rows))]
    highs = [sf(r[3]) for r in recent if sf(r[3])]
    lows = [sf(r[4]) for r in recent if sf(r[4])]
    recent_high = max(highs) if highs else None
    recent_low = min(lows) if lows else None

    # 均线多头/空头排列
    ma_arrangement = "多头排列" if (ma5 and ma10 and ma20 and ma5 > ma10 > ma20) else \
                      "空头排列" if (ma5 and ma10 and ma20 and ma5 < ma10 < ma20) else "混合排列"

    return api_ok({
        "ts_code": ts_code, "trade_date": str(latest[1]) if latest[1] else None,
        "close": close,
        "trend": trend, "trend_level": trend_level,
        "ma_arrangement": ma_arrangement,
        "position": {
            "ma5": position_ma5, "ma10": position_ma10,
            "ma20": position_ma20, "ma60": position_ma60,
        },
        "support": {"s1": s1, "s2": sf(latest[15]) if len(latest) > 15 else None},
        "pressure": {"p1": p1, "p2": sf(latest[16]) if len(latest) > 16 else None},
        "recent_high_10d": recent_high, "recent_low_10d": recent_low,
        "break_signals": break_signals,
        "break_up_signals": break_up_signals,
    })


# ===================== 接口11：综合评分 =====================
@app.route("/api/strategy/score")
@param_required("ts_code")
def strategy_score():
    ts_code = request.args.get("ts_code", "").strip()
    days = int(request.args.get("days", 120))

    price_rows = rows("""
        SELECT trade_date, close, pct_change, volume,
               ma5, ma10, ma20, ma60, ma120, ma250,
               support_1, pressure_1,
               rise_days, fall_days
        FROM stock_daily_price
        WHERE ts_code = %s
        ORDER BY trade_date DESC LIMIT %s
    """, (ts_code, min(days, 250)))

    if not price_rows or len(price_rows) < 20:
        return api_err("数据不足", code=404)

    latest = price_rows[0]
    close = sf(latest[2]); pct = sf(latest[3]); volume = si(latest[4])
    ma5 = sf(latest[5]); ma10 = sf(latest[6]); ma20 = sf(latest[7])
    ma60 = sf(latest[8]); ma120 = sf(latest[9]); ma250 = sf(latest[10])
    s1 = sf(latest[11]); p1 = sf(latest[12])
    rise_days = latest[13] if len(latest) > 13 else 0
    fall_days = latest[14] if len(latest) > 14 else 0

    trend_score = 0.0  # 趋势得分（40分）
    if ma20 and close > ma20: trend_score += 20
    if ma60 and close > ma60: trend_score += 10
    if ma250 and close > ma250: trend_score += 10
    if ma5 and ma10 and ma20 and ma5 > ma10 > ma20: trend_score += 5
    if ma20 and close > ma20 * 1.05: trend_score += 5  # 远离均线加分

    momentum_score = 0.0  # 动量得分（25分）
    if len(price_rows) >= 5:
        pct_5d = sum(sf(r[3]) or 0 for r in price_rows[:5])
        momentum_score += min(15, max(0, pct_5d * 5))
    if len(price_rows) >= 10:
        pct_10d = sum(sf(r[3]) or 0 for r in price_rows[:10])
        momentum_score += min(10, max(0, pct_10d * 3))

    volume_score = 0.0  # 量能得分（15分）
    if len(price_rows) >= 20:
        vols = [si(r[4]) for r in price_rows[:20] if si(r[4])]
        if vols:
            avg_vol = sum(vols) / len(vols)
            vol_ratio = volume / avg_vol if avg_vol else 0
            volume_score = min(15, vol_ratio * 10)

    valuation_score = 50.0  # 估值得分（20分），默认中性
    # 粗估：价格相对位置
    if ma250 and ma250 != 0:
        price_pos = (close - ma250) / ma250 * 100
        if price_pos < 0:
            valuation_score = 70  # 低位低估
        elif price_pos < 20:
            valuation_score = 55  # 正常偏低
        elif price_pos < 50:
            valuation_score = 40  # 正常偏高
        else:
            valuation_score = 25  # 高估

    risk_score = 100.0  # 风险得分（扣分制，100分满分）
    risk_notes = []
    if ma20 and close < ma20:
        risk_score -= 15
        risk_notes.append("价格低于20日线")
    if ma60 and close < ma60:
        risk_score -= 10
        risk_notes.append("价格低于60日线")
    if s1 and close < s1:
        risk_score -= 10
        risk_notes.append("跌破支撑位")
    if fall_days > rise_days * 2 and fall_days > 5:
        risk_score -= 10
        risk_notes.append("连续下跌为主")
    if pct and pct < -5:
        risk_score -= 10
        risk_notes.append("当日大跌超5%")

    # 总分 = 趋势*0.4 + 动量*0.25 + 量能*0.15 + 估值*0.2 - 风险扣分
    raw_total = (trend_score * 0.4 + momentum_score * 0.25 +
                 volume_score * 0.15 + valuation_score * 0.2)
    total_score = max(0, min(100, round(raw_total * (risk_score / 100), 1)))

    return api_ok({
        "ts_code": ts_code, "close": close, "pct_change": pct,
        "total_score": total_score,
        "level": score_to_level(total_score),
        "dimensions": {
            "trend": {"score": round(trend_score, 1), "max": 40,
                       "desc": "趋势与均线位置"},
            "momentum": {"score": round(momentum_score, 1), "max": 25,
                         "desc": "短期动量与涨跌惯性"},
            "volume": {"score": round(volume_score, 1), "max": 15,
                       "desc": "量能配合情况"},
            "valuation": {"score": round(valuation_score, 1), "max": 20,
                          "desc": "相对估值位置（低价位加分）"},
            "risk": {"score": round(risk_score, 1), "max": 100,
                     "desc": "风险状态（扣分制）",
                     "notes": risk_notes},
        },
        "support": s1, "pressure": p1,
        "ma5": ma5, "ma20": ma20, "ma60": ma60,
    })


# ===================== 接口12：每日复盘简报 =====================
@app.route("/api/report/daily")
def report_daily():
    """
    每日市场复盘
    返回：大盘情绪 + 强势板块分析（代替原来的涨停股列表）
    """
    latest = row("SELECT MAX(trade_date) FROM stock_daily_price")
    latest_date = latest[0] if latest else None
    if not latest_date:
        return api_err("无数据", code=404)

    prev_date_row = row("SELECT MAX(trade_date) FROM stock_daily_price WHERE trade_date < %s", (latest_date,))
    prev_date = prev_date_row[0] if prev_date_row else None

    # ── 大盘概览 ────────────────────────────────────────────
    m = row("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN pct_change > 0 THEN 1 ELSE 0 END) AS rise,
               SUM(CASE WHEN pct_change < 0 THEN 1 ELSE 0 END) AS fall,
               SUM(CASE WHEN pct_change > 9.5 THEN 1 ELSE 0 END) AS limit_up,
               SUM(CASE WHEN pct_change < -9.5 THEN 1 ELSE 0 END) AS limit_down,
               ROUND(AVG(pct_change), 2) AS avg_pct
        FROM stock_daily_price WHERE trade_date = %s
    """, (latest_date,))
    total, rise_n, fall_n, limit_up_n, limit_down_n, avg_pct = m

    # ── 板块聚合 ────────────────────────────────────────────
    sector_rows = rows("""
        SELECT b.industry,
               COUNT(*) AS cnt,
               SUM(p.pct_change) / COUNT(*) AS avg_pct,
               SUM(CASE WHEN p.pct_change > 0 THEN 1 ELSE 0 END) AS rise_cnt,
               SUM(CASE WHEN p.pct_change > 9.5 THEN 1 ELSE 0 END) AS limit_up_cnt,
               SUM(CASE WHEN p.pct_change < -9.5 THEN 1 ELSE 0 END) AS limit_down_cnt
        FROM stock_daily_price p
        JOIN stock_basic b ON b.ts_code = p.ts_code
        WHERE p.trade_date = %s AND b.industry IS NOT NULL AND b.industry != ''
        GROUP BY b.industry
        HAVING COUNT(*) >= 3
        ORDER BY avg_pct DESC
    """, (latest_date,))

    # ── 板块内个股明细（用于分析原因）───────────────────────
    # 拉取所有个股数据用于板块内排名
    all_stock_rows = rows("""
        SELECT b.industry, p.ts_code, p.close, p.pct_change, p.volume, p.rise_days
        FROM stock_daily_price p
        JOIN stock_basic b ON b.ts_code = p.ts_code
        WHERE p.trade_date = %s
        AND b.industry IS NOT NULL AND b.industry != ''
        ORDER BY b.industry, p.pct_change DESC
    """, (latest_date,))

    # 按行业分组个股
    from collections import defaultdict
    industry_stocks = defaultdict(list)
    for row2 in all_stock_rows:
        ind = row2[0]
        industry_stocks[ind].append({
            "ts_code": row2[1], "close": sf(row2[2]),
            "pct": sf(row2[3]), "volume": si(row2[4]),
            "rise_days": si(row2[5]),
        })

    # ── 计算情绪分数 + 生成分析 ─────────────────────────────
    emotion_score = 50
    if total:
        rise_ratio = rise_n / total
        if rise_ratio >= 0.7: emotion_score = 90
        elif rise_ratio >= 0.6: emotion_score = 75
        elif rise_ratio >= 0.5: emotion_score = 60
        elif rise_ratio >= 0.4: emotion_score = 45
        else: emotion_score = 30

    market_emotion = (
        "极强赚钱效应 ✦" if emotion_score >= 85 else
        "强势" if emotion_score >= 70 else
        "偏强" if emotion_score >= 55 else
        "偏弱" if emotion_score >= 40 else
        "弱势 ▦"
    )

    # ── 强势板块分析 ────────────────────────────────────────
    sector_analysis = []
    hot_sectors = []
    up_count = 0

    for sr in sector_rows:
        industry = sr[0]
        cnt = int(sr[1]); avg_pct_ind = sf(sr[2])
        rise_cnt = int(sr[3]); limit_up_cnt = int(sr[4])
        fall_cnt = cnt - rise_cnt

        if avg_pct_ind > 0: up_count += 1

        # 个股列表（按涨幅排序）
        stocks_in_ind = industry_stocks.get(industry, [])
        top_stocks = sorted(stocks_in_ind, key=lambda x: -(x["pct"] or 0))[:3]

        # ── 强势原因分析 ──────────────────────────────────
        reasons = []
        if limit_up_cnt >= 2:
            reasons.append(f"板块内{limit_up_cnt}只涨停，领涨效应强")
        elif limit_up_cnt == 1:
            reasons.append(f"有{limit_up_cnt}只涨停，个股带动板块")
        if rise_cnt / cnt >= 0.7 if cnt > 0 else False:
            reasons.append("板块普涨（70%以上个股上涨）")
        if avg_pct_ind >= 3:
            reasons.append(f"平均涨幅{avg_pct_ind:.1f}%，强势领涨")
        elif avg_pct_ind >= 1.5:
            reasons.append(f"平均涨幅{avg_pct_ind:.1f}%，整体偏强")
        elif avg_pct_ind >= 0.5:
            reasons.append("小幅上涨，整体平稳")
        # 看top个股表现
        if top_stocks:
            best = top_stocks[0]
            if best["pct"] and best["pct"] >= 9.5:
                reasons.append(f"龙头{best['ts_code']}涨停，激活板块情绪")
            elif best["pct"] and best["pct"] >= 5:
                reasons.append(f"龙头{best['ts_code']}涨{best['pct']:.1f}%，形成板块效应")
        # 量价配合
        avg_vol = sum(s.get("volume",0) for s in stocks_in_ind) / max(cnt, 1)
        top3_vol = sum(s.get("volume",0) for s in top_stocks[:1]) / max(1, len(top_stocks[:1]))
        if top3_vol > avg_vol * 1.5:
            reasons.append("龙头个股量能放大，资金主动介入")
        # 连续上涨
        rise3_stocks = [s for s in stocks_in_ind if (s.get("rise_days") or 0) >= 3]
        if len(rise3_stocks) >= 2:
            reasons.append(f"板块内{len(rise3_stocks)}只股票连续3日上涨，趋势强劲")

        # 综合判断
        if avg_pct_ind >= 3 and limit_up_cnt >= 1:
            strength = "极强"
        elif avg_pct_ind >= 1.5 and rise_cnt / cnt >= 0.6 if cnt > 0 else False:
            strength = "偏强"
        elif avg_pct_ind >= 0.5:
            strength = "温和"
        elif avg_pct_ind < -1.5 and fall_cnt / cnt >= 0.7 if cnt > 0 else False:
            strength = "偏弱"
        else:
            strength = "震荡"

        analysis_text = "；".join(reasons) if reasons else f"{industry}整体平稳，跟随大盘波动"

        # 情绪评分（板块级别）
        ind_emotion = int(50 + avg_pct_ind * 8 + rise_cnt / cnt * 20 - fall_cnt / cnt * 10)
        ind_emotion = max(0, min(100, ind_emotion))

        sector_analysis.append({
            "industry": industry,
            "stock_count": cnt,
            "rise_count": rise_cnt,
            "fall_count": fall_cnt,
            "avg_pct": round(avg_pct_ind, 2),
            "limit_up_count": limit_up_cnt,
            "limit_down_count": limit_up_cnt,
            "emotion_score": ind_emotion,
            "strength": strength,
            "analysis": analysis_text,
            "top_stocks": [
                {"ts_code": s["ts_code"], "pct": round(s["pct"], 2) if s["pct"] else 0,
                 "close": s["close"], "rise_days": s["rise_days"]}
                for s in top_stocks[:3]
            ],
        })
        if avg_pct_ind >= 1.5 or limit_up_cnt >= 1:
            hot_sectors.append(industry)

    # ── 写入 sector_analysis 表 ───────────────────────────
    for sec in sector_analysis:
        try:
            row("""
                INSERT INTO sector_analysis
                (trade_date, industry, avg_pct, rise_count, stock_count, emotion_score, analysis)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                  avg_pct=VALUES(avg_pct), rise_count=VALUES(rise_count),
                  stock_count=VALUES(stock_count), emotion_score=VALUES(emotion_score),
                  analysis=VALUES(analysis)
            """, (latest_date, sec["industry"], sec["avg_pct"], sec["rise_count"],
                  sec["stock_count"], sec["emotion_score"], sec["analysis"]))
        except Exception:
            pass

    # ── 市场关注点 ─────────────────────────────────────────
    concerns = []
    if limit_down_n and limit_down_n >= 5:
        concerns.append(f"{limit_down_n}只跌停，小心恐慌情绪蔓延")
    if avg_pct and avg_pct < -1:
        concerns.append(f"大盘均跌{abs(avg_pct):.1f}%，整体偏弱")
    if emotion_score <= 35:
        concerns.append("市场情绪低迷，观望为主")
    if up_count == 0:
        concerns.append("所有板块均下跌，等待企稳信号")
    if not concerns:
        concerns = ["市场无明显异常，关注强势板块机会"]

    return api_ok({
        "trade_date": str(latest_date),
        "market": {
            "total": int(total or 0),
            "rise_count": int(rise_n or 0),
            "fall_count": int(fall_n or 0),
            "limit_up_count": int(limit_up_n or 0),
            "limit_down_count": int(limit_down_n or 0),
            "avg_pct": float(avg_pct or 0),
            "emotion_score": emotion_score,
            "market_emotion": market_emotion,
        },
        "sector_analysis": sector_analysis,
        "hot_sectors": hot_sectors[:10],
        "concerns": concerns,
    })


# ===================== 健康检查 & 状态 =====================
@app.route("/health")
def health():
    try:
        row("SELECT 1")
        return jsonify({"status": "ok", "time": datetime.datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500


@app.route("/api/status")
def api_status():
    """数据库状态"""
    try:
        t1 = row("SELECT COUNT(*) FROM stock_basic")
        t2 = row("SELECT COUNT(*) FROM stock_daily_price")
        t3 = row("SELECT MAX(trade_date) FROM stock_daily_price")
        t4 = row("SELECT COUNT(DISTINCT trade_date) FROM stock_daily_price")
        t5 = row("SELECT COUNT(*) FROM stock_daily_indicator")
        t6 = row("SELECT COUNT(*) FROM stock_market_overview")
        return api_ok({
            "stock_basic": t1[0] if t1 else 0,
            "daily_price": t2[0] if t2 else 0,
            "daily_indicator": t5[0] if t5 else 0,
            "market_overview": t6[0] if t6 else 0,
            "latest_date": str(t3[0]) if t3 and t3[0] else None,
            "trading_days": t4[0] if t4 else 0,
        })
    except Exception as e:
        return api_err(str(e))


# ===================== 接口13：股票搜索（按名称/代码模糊搜索）=====================
@app.route("/api/search")
def search_stock():
    """按名称或代码模糊搜索股票，支持按热度/相关性排序"""
    kw = request.args.get("q", "").strip()
    if not kw:
        return api_err("请提供搜索关键词", code=400)

    limit = min(int(request.args.get("limit", 20)), 50)

    # 优先精确匹配，其次模糊匹配
    sql = """
        SELECT ts_code, symbol, name, industry, market
        FROM stock_basic
        WHERE is_active = 1
        AND (name LIKE %s OR symbol LIKE %s OR ts_code LIKE %s)
        ORDER BY
            CASE
                WHEN name = %s THEN 1
                WHEN symbol = %s THEN 2
                WHEN name LIKE %s THEN 3
                ELSE 4
            END,
            name ASC
        LIMIT %s
    """
    like_kw = f"%{kw}%"
    rows_result = rows(sql, (like_kw, like_kw, like_kw, kw, kw, f"{kw}%", limit))

    items = []
    for r in rows_result:
        ts_code = r[0]
        # 查最新价格
        price_row = row("""
            SELECT close, pct_change FROM stock_daily_price
            WHERE ts_code=%s ORDER BY trade_date DESC LIMIT 1
        """, (ts_code,))
        items.append({
            "ts_code": ts_code,
            "symbol": r[1],
            "name": r[2],
            "industry": r[3],
            "market": r[4],
            "close": sf(price_row[0]) if price_row else None,
            "pct_change": sf(price_row[1]) if price_row else None,
        })

    return api_ok({"keyword": kw, "items": items})


# ===================== 接口14：趋势跟进（MA金叉·严格版）=====================
@app.route("/api/strategy/golden_cross")
def strategy_golden_cross():
    """
    【严格筛选】5日线上穿20日线（MA金叉）
    四个必过条件（全部满足）：
    1. 成交量：金叉前2日均量 ≥ 近20日均量的1.2倍
    2. MA20趋势：3交易日前MA20 ≤ 今日MA20（非下行）
    3. 股价位置：近3月跌幅≥20%  或  金叉前已横盘（变异系数<6%）
    4. 均线站稳：金叉当日收盘价同时站稳 MA5、MA10、MA20
    """
    top_n = min(int(request.args.get("top", 100)), 300)
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(int(request.args.get("page_size", 50)), 100)

    latest_date_row = row("SELECT MAX(trade_date) FROM stock_daily_price")
    latest_date = latest_date_row[0] if latest_date_row else None
    if not latest_date:
        return api_err("无数据", code=404)

    prev_date_row = row("""
        SELECT MAX(trade_date) FROM stock_daily_price WHERE trade_date < %s
    """, (latest_date,))
    prev_date = prev_date_row[0] if prev_date_row else None

    # 先找金叉候选股
    if prev_date:
        cand_rows = rows("""
            SELECT p1.ts_code, p1.close, p1.volume, p1.ma5, p1.ma10, p1.ma20, p1.pct_change
            FROM stock_daily_price p1
            JOIN stock_daily_price p0 ON p0.ts_code = p1.ts_code AND p0.trade_date = %s
            WHERE p1.trade_date = %s
            AND p1.ma5 IS NOT NULL AND p1.ma20 IS NOT NULL
            AND p1.ma5 > p1.ma20
            AND (p0.ma5 <= p0.ma20 OR p0.ma5 IS NULL)
        """, (prev_date, latest_date))
    else:
        cand_rows = rows("""
            SELECT ts_code, close, volume, ma5, ma10, ma20, pct_change
            FROM stock_daily_price
            WHERE trade_date = %s
            AND ma5 IS NOT NULL AND ma20 IS NOT NULL AND ma5 > ma20
        """, (latest_date,))

    if not cand_rows:
        return api_ok({
            "trade_date": str(latest_date) if latest_date else None,
            "prev_date": str(prev_date) if prev_date else None,
            "total": 0, "page": 1, "page_size": page_size, "pages": 1,
            "items": [],
        })

    # 批量拉取所有候选股的历史数据（一次查询搞定）
    ts_codes = [r[0] for r in cand_rows]
    placeholders = ",".join(["%s"] * len(ts_codes))
    hist_rows = rows(f"""
        SELECT ts_code, trade_date, close, high, low, volume, ma5, ma10, ma20, pct_change
        FROM stock_daily_price
        WHERE ts_code IN ({placeholders})
        AND trade_date >= %s - INTERVAL 90 DAY
        ORDER BY ts_code, trade_date DESC
    """, ts_codes + [latest_date])

    # 按股票分组
    hist_map = {}
    for h in hist_rows:
        ts = h[0]
        if ts not in hist_map:
            hist_map[ts] = []
        hist_map[ts].append(h)

    golden_items = []
    for r in cand_rows:
        ts_code = r[0]
        close = sf(r[1]); vol_today = si(r[2])
        ma5 = sf(r[3]); ma10 = sf(r[4]); ma20 = sf(r[5])

        bars = hist_map.get(ts_code, [])
        if len(bars) < 25:
            continue

        # === 条件4：收盘站稳MA5/MA10/MA20 ===
        if not (close and ma5 and ma10 and ma20 and close >= ma5 and close >= ma10 and close >= ma20):
            continue

        # === 条件1：成交量验证（前2日均量 ≥ 近20日均量×1.2）===
        vols = [si(b[5]) for b in bars[:20] if si(b[5])]
        avg20 = sum(vols) / len(vols) if vols else 0
        vols2 = [si(b[5]) for b in bars[:2] if si(b[5])]
        avg2d = sum(vols2) / len(vols2) if vols2 else 0
        if avg20 > 0 and avg2d < avg20 * 1.2:
            continue

        # === 条件2：MA20趋势（3交易日前 ≤ 今日，非下行）===
        ma20s = [sf(b[8]) for b in bars if b[8] is not None]
        if len(ma20s) < 4:
            continue
        if not (ma20s[3] <= ma20s[0]):
            continue

        # === 条件3：股价位置 ===
        # 近3月高点
        highs = [sf(b[3]) for b in bars[1:61] if b[3] is not None]
        high60 = max(highs) if highs else None
        pct_3m = round((close - high60) / high60 * 100, 2) if high60 and high60 > 0 else 0
        low_3m = pct_3m <= -20

        # 横盘（近1个月CV<6%）
        c22 = [sf(b[2]) for b in bars[1:23] if b[2] is not None]
        consolidation_ok = False
        if len(c22) >= 20:
            avg_c = sum(c22) / len(c22)
            if avg_c > 0:
                std_c = math.sqrt(sum((x - avg_c) ** 2 for x in c22) / len(c22))
                consolidation_ok = (std_c / avg_c) < 0.06

        if not (low_3m or consolidation_ok):
            continue

        # === 通过全部条件 ===
        pct_5d = sum(sf(b[9]) or 0 for b in bars[:5])
        pct_10d = sum(sf(b[9]) or 0 for b in bars[:10])
        cross_strength = round((ma5 - ma20) / ma20 * 100, 4) if ma20 else None
        vol_ratio = round(avg2d / avg20, 2) if avg20 > 0 else None

        golden_items.append({
            "ts_code": ts_code,
            "close": close,
            "pct_change": sf(r[6]),
            "volume": vol_today,
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "rise_5d": round(pct_5d, 2),
            "rise_10d": round(pct_10d, 2),
            "cross_strength": cross_strength,
            "vol_ratio": vol_ratio,
            "pct_3m": pct_3m,
            "low_3m": low_3m,
            "consolidation": consolidation_ok,
            "trade_date": str(latest_date) if latest_date else None,
        })

    # ── 补充名称、行业，并执行强制排除规则 ──
    ts_list = [x["ts_code"] for x in golden_items]
    if ts_list:
        name_map = {}
        name_rows = rows("""
            SELECT ts_code, name, industry FROM stock_basic
            WHERE ts_code IN (%s)
        """ % (",".join(["%s"] * len(ts_list))), ts_list)
        for nr in name_rows:
            name_map[nr[0]] = {"name": nr[1], "industry": nr[2]}

        filtered_items = []
        for item in golden_items:
            info = name_map.get(item["ts_code"], {})
            name = info.get("name") or ""
            industry = info.get("industry") or "未知"
            item["name"] = name
            item["industry"] = industry

            # ── 排除规则1：ST/*ST/退市预警 ──
            if "*" in name or "ST" in name or "退" in name:
                continue

            # ── 排除规则3：金叉后3日成交量持续萎缩 ──
            # bars[0]=今日(金叉日), bars[1]=昨日, bars[2]=2日前, bars[3]=3日前
            bars = hist_map.get(item["ts_code"], [])
            if len(bars) >= 4:
                v0 = si(bars[0][5]) if bars[0] else 0  # 金叉当日
                v1 = si(bars[1][5]) if bars[1] else 0  # 后第1日
                v2 = si(bars[2][5]) if bars[2] else 0  # 后第2日
                v3 = si(bars[3][5]) if bars[3] else 0  # 后第3日
                # 持续萎缩：后3日量都比金叉当日小，且逐日递减
                post_vols = [v1, v2, v3]
                if v0 > 0 and all(v < v0 for v in post_vols) and post_vols == sorted(post_vols, reverse=True):
                    # 后3日量全小于金叉当日，且逐日递减 = 持续萎缩
                    continue

            filtered_items.append(item)

        golden_items = filtered_items

    # 排序：按金叉强度降序
    golden_items.sort(key=lambda x: -(x["cross_strength"] or 0))

    total = len(golden_items)
    start = (page - 1) * page_size
    page_items = golden_items[start:start + page_size]

    # ── 自动写入追踪记录 ──
    for it in golden_items:
        try:
            row("""
                INSERT INTO golden_cross_track
                (ts_code, name, industry, trade_date, close, ma5, ma20,
                 cross_strength, vol_ratio, pct_3m, consolidation, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)
                ON DUPLICATE KEY UPDATE
                  name=VALUES(name), industry=VALUES(industry),
                  close=VALUES(close), ma5=VALUES(ma5), ma20=VALUES(ma20),
                  cross_strength=VALUES(cross_strength), vol_ratio=VALUES(vol_ratio),
                  pct_3m=VALUES(pct_3m), consolidation=VALUES(consolidation)
            """, (
                it["ts_code"], it.get("name",""), it.get("industry",""),
                latest_date, it["close"], it["ma5"], it["ma20"],
                it["cross_strength"], it["vol_ratio"],
                it.get("pct_3m"), 1 if it.get("consolidation") else 0,
            ))
        except Exception:
            pass

    # ── 批量获取实时价格（新浪接口）────
    if page_items:
        sina_list = ",".join(
            ("sz" if tc.endswith(".SZ") else "sh") + tc.split(".")[0]
            for tc in [x["ts_code"] for x in page_items]
        )
        try:
            import urllib.request, re as _re
            req = urllib.request.Request(
                f"https://hq.sinajs.cn/list={sina_list}",
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = resp.read().decode("gbk", errors="ignore")
            for match in _re.finditer(r'hq_str_(\w+)="([^"]+)"', raw):
                sinacode = match.group(1)
                fields = match.group(2).split(",")
                # 还原 ts_code
                prefix = "sz" if sinacode.startswith("sz") else "sh"
                ts = sinacode[2:] + (".SZ" if prefix == "sz" else ".SH")
                if len(fields) > 8 and fields[3] and fields[3] != "0":
                    rt_p = sf(fields[3])
                    rt_y = sf(fields[2])
                    rt_pct = round((rt_p - rt_y) / rt_y * 100, 2) if rt_p and rt_y else None
                    rt_time = (fields[30] + " " + fields[31]) if len(fields) > 31 and fields[31] else (fields[30] if len(fields) > 30 and fields[30] else None)
                    for it in page_items:
                        if it["ts_code"] == ts:
                            it["rt_price"] = rt_p
                            it["rt_pct"] = rt_pct
                            it["rt_time"] = rt_time
                            break
        except Exception:
            pass

    return api_ok({
        "trade_date": str(latest_date) if latest_date else None,
        "prev_date": str(prev_date) if prev_date else None,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 1,
        "items": page_items,
    })



# ===================== 接口16：MACD趋势信号（严格版）=====================
@app.route("/api/strategy/macd_cross")
def strategy_macd_cross():
    """
    【MACD + 量价综合筛选】严格版
    必过条件（全部满足）：
    1. MACD金叉：DIF上穿DEA（DIF≥DEA 且 昨日DIF<昨日DEA）
    2. 量能确认：今日成交量 ≥ 近20日均量 × 1.3
    3. 价在均上：收盘 > MA20（非破位）
    4. DIF>0：多头区间
    5. 近5日均量 ≥ 近20日均量 × 0.9（持续放量，不是突然爆量）

    选股规则：从通过全部条件的股票中取综合评分TOP3
    综合评分 = 金叉强度(40%) + 量能质量(30%) + 趋势位置(30%)
    """
    page_size = 3  # 固定3只

    # 取有MA20数据的最新日期
    latest_date_row = row("SELECT MAX(trade_date) FROM stock_daily_price WHERE ma20 IS NOT NULL")
    latest_date = latest_date_row[0] if latest_date_row else None
    if not latest_date:
        return api_err("无有效数据（MA20未计算）", code=404)

    prev_date_row = row("SELECT MAX(trade_date) FROM stock_daily_price WHERE trade_date < %s AND ma20 IS NOT NULL", (latest_date,))
    prev_date = prev_date_row[0] if prev_date_row else None

    # 候选：ma5>ma20（金叉当天），价格站稳均线
    cand_rows = rows("""
        SELECT p1.ts_code, b.name, b.industry,
               p1.close, p1.volume, p1.pct_change,
               p1.ma5, p1.ma10, p1.ma20
        FROM stock_daily_price p1
        JOIN stock_basic b ON b.ts_code = p1.ts_code
        JOIN stock_daily_price p0 ON p0.ts_code = p1.ts_code AND p0.trade_date = %s
        WHERE p1.trade_date = %s
        AND p1.ma5 IS NOT NULL AND p1.ma20 IS NOT NULL
        AND p1.ma5 > p1.ma20
        AND p1.close > p1.ma20
        AND b.is_active = 1
        AND b.name NOT LIKE %s AND b.name NOT LIKE %s
    """, (prev_date, latest_date, '%%ST%%', '%%*%%'))

    if not cand_rows:
        return api_ok({
            "trade_date": str(latest_date), "prev_date": str(prev_date),
            "total": 0, "page": 1, "page_size": page_size, "pages": 1, "items": [],
        })

    # 批量拉取完整历史（按日期升序：旧→新）
    ts_codes = [r[0] for r in cand_rows]
    placeholders = ",".join(["%s"] * len(ts_codes))
    hist_rows = rows(f"""
        SELECT ts_code, trade_date, close, volume, pct_change
        FROM stock_daily_price
        WHERE ts_code IN ({placeholders})
        AND trade_date >= %s - INTERVAL 90 DAY
        ORDER BY ts_code, trade_date ASC
    """, ts_codes + [latest_date])

    hist_map = {}
    for h in hist_rows:
        ts = h[0]
        if ts not in hist_map:
            hist_map[ts] = []
        hist_map[ts].append(h)

    def calc_macd(closes, vols):
        """
        正确EMA算法：全量迭代，返回 (dif_t, dea_t, dif_y, dea_y, hist_t)
        closes: [旧,...,新]
        """
        n1, n2, n3 = 12, 26, 9
        if len(closes) < n2 + n3:
            return None
        k1 = 2.0 / (n1 + 1)
        k2 = 2.0 / (n2 + 1)
        k3 = 2.0 / (n3 + 1)
        # 初始化EMA为SMA
        e12 = sum(closes[:n1]) / n1
        e26 = sum(closes[:n2]) / n2
        dif_series = []
        # 从第n1个开始算EMA12（因为前n1-1个不够）
        for i, c in enumerate(closes):
            if i >= n1:
                e12 = c * k1 + e12 * (1 - k1)
            if i >= n2:
                e26 = c * k2 + e26 * (1 - k2)
            if i >= n1:
                dif_series.append(e12 - e26)
        if len(dif_series) < n3:
            return None
        # DEA: 从第n3个开始算
        e_dea = sum(dif_series[:n3]) / n3
        dea_series = []
        for i, d in enumerate(dif_series):
            if i >= n3:
                e_dea = d * k3 + e_dea * (1 - k3)
            dea_series.append(e_dea)
        dif_t = dif_series[-1]
        dif_y = dif_series[-2]
        dea_t = dea_series[-1]
        dea_y = dea_series[-2]
        return dif_t, dea_t, dif_y, dea_y, (dif_t - dea_t) * 2

    valid_items = []
    for r in cand_rows:
        ts_code = r[0]; name = r[1]; industry = r[2]
        close = sf(r[3]); vol_today = si(r[4]); pct = sf(r[5])
        ma5 = sf(r[6]); ma20 = sf(r[8])

        bars = hist_map.get(ts_code, [])
        if len(bars) < 40:
            continue

        closes = [sf(b[2]) for b in bars if b[2] is not None]
        vols_list = [si(b[3]) for b in bars if b[3] is not None]

        # 计算MACD
        macd = calc_macd(closes, vols_list)
        if macd is None:
            continue
        dif_t, dea_t, dif_y, dea_y, hist_t = macd

        # 条件4：DIF > 0
        if not (dif_t and dif_t > 0):
            continue

        # 条件1：MACD金叉
        if not (dif_y is not None and dea_y is not None and dif_y < dea_y and dif_t >= dea_t):
            continue

        # 条件2：量能
        avg_vol_20 = sum(vols_list[-20:]) / min(20, len(vols_list)) if vols_list else 0
        avg_vol_5 = sum(vols_list[-5:]) / min(5, len(vols_list)) if vols_list else 0
        if avg_vol_20 > 0 and vol_today < avg_vol_20 * 1.3:
            continue

        # 条件5：持续放量
        if avg_vol_20 > 0 and avg_vol_5 < avg_vol_20 * 0.9:
            continue

        # 综合评分
        cross_strength = round((dif_t - dea_t) / abs(dea_t) * 100, 4) if dea_t != 0 else 0
        vol_ratio = round(vol_today / avg_vol_20, 2) if avg_vol_20 > 0 else 0
        trend_pos = round((close - ma20) / ma20 * 100, 2) if ma20 else 0
        score = round(cross_strength * 0.4 + vol_ratio * 15 * 0.3 + trend_pos * 1.5 * 0.3)

        pct_5d = sum(sf(b[4]) or 0 for b in bars[-5:])

        valid_items.append({
            "ts_code": ts_code, "name": name, "industry": industry or "未知",
            "close": close, "pct_change": pct,
            "ma5": ma5, "ma20": ma20,
            "dif": round(dif_t, 4), "dea": round(dea_t, 4),
            "macd_hist": round(hist_t, 4),
            "vol_ratio": vol_ratio,
            "cross_strength": cross_strength,
            "trend_pos": trend_pos,
            "rise_5d": round(pct_5d, 2),
            "avg_vol_5": round(avg_vol_5, 0), "avg_vol_20": round(avg_vol_20, 0),
            "score": score,
        })

    valid_items.sort(key=lambda x: -x["score"])
    total = len(valid_items)
    page_items = valid_items[:page_size]

    # 写入追踪表
    for it in valid_items:
        try:
            row("""
                INSERT INTO macd_cross_track
                (ts_code, name, trade_date, close, pct_change, dif, dea, macd_hist, vol_ratio, score)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                  name=VALUES(name), close=VALUES(close), pct_change=VALUES(pct_change),
                  dif=VALUES(dif), dea=VALUES(dea), macd_hist=VALUES(macd_hist),
                  vol_ratio=VALUES(vol_ratio), score=VALUES(score)
            """, (it["ts_code"], it["name"], latest_date, it["close"], it["pct_change"],
                  it["dif"], it["dea"], it["macd_hist"], it["vol_ratio"], it["score"]))
        except Exception:
            pass

    return api_ok({
        "trade_date": str(latest_date), "prev_date": str(prev_date),
        "total": total, "page": 1, "page_size": page_size,
        "pages": 1,
        "items": page_items,
    })


# ===================== 接口15：追踪记录写入 + 3日追踪更新 ======================
@app.route("/api/strategy/golden_cross/track_update", methods=["POST"])
def track_update():
    """
    对所有追踪中的股票，更新1/2/3日涨跌幅数据
    """
    # 更新所有status=0的记录
    pending_rows = rows("""
        SELECT id, ts_code, trade_date, close FROM golden_cross_track
        WHERE status = 0
    """)

    if not pending_rows:
        return api_ok({"updated": 0})

    updated = 0
    for row in pending_rows:
        rec_id, ts_code, sel_date, sel_close = row[0], row[1], row[2], row[3]
        if not sel_close:
            continue

        # 找入选后第1/2/3个交易日
        price_rows = rows("""
            SELECT trade_date, close FROM stock_daily_price
            WHERE ts_code = %s AND trade_date > %s
            ORDER BY trade_date ASC LIMIT 3
        """, (ts_code, sel_date))

        p1 = price_rows[0] if len(price_rows) >= 1 else None
        p2 = price_rows[1] if len(price_rows) >= 2 else None
        p3 = price_rows[2] if len(price_rows) >= 3 else None

        pct_1d = pct_2d = pct_3d = None
        status = 0

        if p1:
            pct_1d = round((sf(p1[1]) - sf(sel_close)) / sf(sel_close) * 100, 4)
        if p2:
            pct_2d = round((sf(p2[1]) - sf(sel_close)) / sf(sel_close) * 100, 4)
        if p3:
            pct_3d = round((sf(p3[1]) - sf(sel_close)) / sf(sel_close) * 100, 4)

        if p3:
            status = 1  # 3日追踪完成

        row("""
            UPDATE golden_cross_track
            SET pct_1d = %s, pct_2d = %s, pct_3d = %s, status = %s
            WHERE id = %s
        """, (pct_1d, pct_2d, pct_3d, status, rec_id))
        updated += 1

    return api_ok({"updated": updated})

# ===================== 接口16：读取追踪记录页面 ======================
@app.route("/api/strategy/golden_cross/track")
def track_list():
    """
    返回所有追踪记录，含3日追踪结果
    """
    status_filter = request.args.get("status", "")  # 空=全部, 0=追踪中, 1=已完成
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(int(request.args.get("page_size", 30)), 100)

    where = ""
    if status_filter == "0":
        where = "WHERE g.status = 0"
    elif status_filter == "1":
        where = "WHERE g.status = 1"

    total_row = row(f"SELECT COUNT(*) FROM golden_cross_track g {where}")
    total = total_row[0] if total_row else 0

    offset = (page - 1) * page_size
    items = rows(f"""
        SELECT g.id, g.ts_code, g.name, g.industry, g.trade_date,
               g.close, g.ma5, g.ma20, g.cross_strength, g.vol_ratio,
               g.pct_3m, g.consolidation,
               g.pct_1d, g.pct_2d, g.pct_3d, g.status, g.created_at
        FROM golden_cross_track g
        {where}
        ORDER BY g.trade_date DESC, g.id DESC
        LIMIT %s OFFSET %s
    """, (page_size, offset))

    records = []
    for r in items:
        records.append({
            "id": r[0], "ts_code": r[1], "name": r[2], "industry": r[3] or "未知",
            "trade_date": str(r[4]) if r[4] else None,
            "close": sf(r[5]),
            "ma5": sf(r[6]), "ma20": sf(r[7]),
            "cross_strength": sf(r[8]),
            "vol_ratio": sf(r[9]),
            "pct_3m": sf(r[10]),
            "consolidation": bool(r[11]),
            "pct_1d": sf(r[12]),
            "pct_2d": sf(r[13]),
            "pct_3d": sf(r[14]),
            "status": r[15],
            "created_at": str(r[16]) if r[16] else None,
        })

    # ── 批量获取实时价格（给status=0的追踪中股票算实时累计涨幅）────
    ongoing = [rec for rec in records if rec["status"] == 0]
    if ongoing:
        sina_list = ",".join(
            ("sz" if tc.endswith(".SZ") else "sh") + tc.split(".")[0]
            for tc in [x["ts_code"] for x in ongoing]
        )
        try:
            import urllib.request as _ur2, re as _re2
            req = _ur2.Request(
                f"https://hq.sinajs.cn/list={sina_list}",
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
            )
            with _ur2.urlopen(req, timeout=5) as resp:
                raw = resp.read().decode("gbk", errors="ignore")
            for match in _re2.finditer(r'hq_str_(\w+)="([^"]+)"', raw):
                sinacode = match.group(1)
                fields = match.group(2).split(",")
                prefix = "sz" if sinacode.startswith("sz") else "sh"
                ts = sinacode[2:] + (".SZ" if prefix == "sz" else ".SH")
                if len(fields) > 8 and fields[3] and fields[3] != "0":
                    rt_p = sf(fields[3])
                    rt_y = sf(fields[2])
                    for rec in records:
                        if rec["ts_code"] == ts and rec["status"] == 0:
                            rec["rt_price"] = rt_p
                            rec["rt_pct"] = round((rt_p - rt_y) / rt_y * 100, 2) if rt_p and rt_y else None
                            # 实时相对入选日收盘的累计涨跌幅
                            if rt_p and rec["close"]:
                                rec["rt_cum_pct"] = round((rt_p - rec["close"]) / rec["close"] * 100, 2)
                            break
        except Exception:
            pass

    return api_ok({
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 1,
        "items": records,
    })

# ===================== 接口17：金叉入选时自动写入追踪记录 ======================
@app.route("/api/strategy/golden_cross/record", methods=["POST"])
def record_golden_cross():
    """
    接收金叉结果，写入追踪记录表
    """
    data = request.get_json(force=True)
    items = data.get("items", [])
    trade_date = data.get("trade_date")
    if not items or not trade_date:
        return api_err("缺少数据", code=400)

    recorded = 0
    for it in items:
        ts_code = it.get("ts_code")
        if not ts_code:
            continue
        try:
            row("""
                INSERT INTO golden_cross_track
                (ts_code, name, industry, trade_date, close, ma5, ma20,
                 cross_strength, vol_ratio, pct_3m, consolidation, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)
                ON DUPLICATE KEY UPDATE
                  name=VALUES(name), industry=VALUES(industry),
                  close=VALUES(close), ma5=VALUES(ma5), ma20=VALUES(ma20),
                  cross_strength=VALUES(cross_strength), vol_ratio=VALUES(vol_ratio),
                  pct_3m=VALUES(pct_3m), consolidation=VALUES(consolidation)
            """, (
                ts_code, it.get("name",""), it.get("industry",""), trade_date,
                it.get("close"), it.get("ma5"), it.get("ma20"),
                it.get("cross_strength"), it.get("vol_ratio"),
                it.get("pct_3m"), 1 if it.get("consolidation") else 0,
            ))
            recorded += 1
        except Exception:
            pass

    return api_ok({"recorded": recorded})

@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

@app.errorhandler(404)
def not_found(e):
    return api_err("接口不存在", code=404)

@app.errorhandler(500)
# ===================== 接口17：稳中向好趋势评分 =====================
@app.route("/api/strategy/trend_score")
def strategy_trend_score():
    """
    稳中向好趋势评分 | 总分100分 | 6大维度各20分
    ts_code: 股票代码
    """
    ts_code = request.args.get("ts_code", "").strip()
    if not ts_code:
        return api_err("缺少ts_code参数", code=400)

    # 取足够历史（至少60日）
    rows_data = rows("""
        SELECT trade_date, open, close, high, low, volume, pct_change
        FROM stock_daily_price
        WHERE ts_code = %s
        ORDER BY trade_date ASC
        LIMIT 120
    """, (ts_code,))

    if not rows_data or len(rows_data) < 20:
        return api_err("历史数据不足，无法评分", code=404)

    # 转为正序列表
    bars = [(
        str(r[0]),        # trade_date
        float(r[1] or 0), # open
        float(r[2] or 0), # close
        float(r[3] or 0), # high
        float(r[4] or 0), # low
        float(r[5] or 0), # volume
        float(r[6] or 0), # pct_change
    ) for r in rows_data]

    N = len(bars)
    today = bars[-1]
    yest  = bars[-2] if N >= 2 else None

    # ─── 工具函数 ───────────────────────────────────────────────
    def _ma(data, period):
        d = [x for x in data if x is not None]
        if len(d) < period:
            return None
        return sum(d[-period:]) / period

    def _avg(data, n):
        d = [x for x in data if x is not None]
        if len(d) < n:
            return None
        return sum(d[-n:]) / min(n, len(d))

    def _max(data, n=None):
        d = data if n is None else data[-n:]
        d = [x for x in d if x is not None]
        return max(d) if d else None

    def _min(data, n=None):
        d = data if n is None else data[-n:]
        d = [x for x in d if x is not None]
        return min(d) if d else None

    # ─── 价格序列 ───────────────────────────────────────────────
    closes  = [b[2] for b in bars]  # 旧→新
    opens   = [b[1] for b in bars]
    highs   = [b[3] for b in bars]
    lows    = [b[4] for b in bars]
    vols    = [b[5] for b in bars]
    pcts    = [b[6] for b in bars]

    today_close = closes[-1]
    today_vol   = vols[-1]

    # ─── 均线 ─────────────────────────────────────────────────
    ma5_list  = [_ma(closes[:i+1], 5)  for i in range(N)]
    ma10_list = [_ma(closes[:i+1], 10) for i in range(N)]
    ma20_list = [_ma(closes[:i+1], 20) for i in range(N)]
    ma60_list = [_ma(closes[:i+1], 60) for i in range(N)]
    ma5_t  = ma5_list[-1]
    ma10_t = ma10_list[-1]
    ma20_t = ma20_list[-1]
    ma60_t = ma60_list[-1]

    # MA20趋势：前5日均值 vs 再前5日均值
    ma20_5d_avg_cur = _avg(ma20_list[-5:], 5)  # 近5日MA20均值
    ma20_5d_avg_old = _avg(ma20_list[-10:-5], 5)  # 再前5日MA20均值
    ma20_flat_or_up = (ma20_5d_avg_cur is not None and ma20_5d_avg_old is not None
                       and ma20_5d_avg_cur >= ma20_5d_avg_old)

    # MA60趋势
    ma60_5d_avg_cur = _avg(ma60_list[-5:], 5)
    ma60_5d_avg_old = _avg(ma60_list[-10:-5], 5)
    ma60_not_down = (ma60_5d_avg_cur is not None and ma60_5d_avg_old is not None
                     and ma60_5d_avg_cur >= ma60_5d_avg_old)

    # 近期低点：近20日最低点逐步抬高
    def low_n(n):
        mn = _min(lows[-n:], n) if len(lows) >= n else None
        return mn
    recent_lows = []
    for i in range(3, 0, -1):
        if len(lows) >= i * 5:
            recent_lows.append(_min(lows[-(i*5):], i*5))
    lows_rising = all(recent_lows[i] <= recent_lows[i+1]
                     for i in range(len(recent_lows)-1)) if len(recent_lows) >= 2 else False

    # ─── MACD ─────────────────────────────────────────────────
    def calc_macd_vals(close_series, n1=12, n2=26, n3=9):
        cs = close_series
        if len(cs) < n2 + n3:
            return None, None, None, None
        k1 = 2.0/(n1+1); k2 = 2.0/(n2+1); k3 = 2.0/(n3+1)
        e12 = sum(cs[:n1])/n1; e26 = sum(cs[:n2])/n2
        dif_list = []
        for i, c in enumerate(cs):
            if i >= n1: e12 = c*k1 + e12*(1-k1)
            if i >= n2: e26 = c*k2 + e26*(1-k2)
            if i >= n1: dif_list.append(e12 - e26)
        if len(dif_list) < n3:
            return None, None, None, None
        e_dea = sum(dif_list[:n3])/n3
        dea_list = []
        for i, d in enumerate(dif_list):
            if i >= n3: e_dea = d*k3 + e_dea*(1-k3)
            dea_list.append(e_dea)
        dif_t = dif_list[-1]; dea_t = dea_list[-1]
        dif_y = dif_list[-2] if len(dif_list) >= 2 else None
        dea_y = dea_list[-2] if len(dea_list) >= 2 else None
        hist_t = (dif_t - dea_t) * 2
        # 绿柱缩短：DIF更接近DEA（hist值变大/变红）
        return dif_t, dea_t, dif_y, dea_y, hist_t

    dif_t, dea_t, dif_y, dea_y, macd_hist_t = calc_macd_vals(closes)

    # 近5日MACD柱（判断是否在缩短）
    def get_macd_hist_n(n):
        cs = closes[:len(closes)-n] if n > 0 else closes
        dt, deat, dyt, deayt, ht = calc_macd_vals(cs)
        return ht
    macd_hist_2d_ago = get_macd_hist_n(2)  # 2天前
    macd_hist_1d_ago = get_macd_hist_n(1)  # 1天前

    # 金叉：dif_y < dea_y 且 dif_t >= dea_t
    macd_golden_cross = (dif_y is not None and dea_y is not None
                          and dif_y < dea_y and dif_t >= dea_t)

    # ─── RSI ─────────────────────────────────────────────────
    def calc_rsi(close_series, period=14):
        cs = close_series
        if len(cs) < period + 1:
            return None
        gains = []; losses = []
        for i in range(1, len(cs)):
            delta = cs[i] - cs[i-1]
            gains.append(max(delta, 0))
            losses.append(max(-delta, 0))
        if len(gains) < period:
            return None
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    rsi_t   = calc_rsi(closes)
    rsi_5d  = calc_rsi(closes[:-1]) if len(closes) > 1 else None

    def calc_kdj(high_series, low_series, close_series, n=9, m1=3, m2=3):
        hs = high_series; ls = low_series; cs = close_series
        if len(cs) < n:
            return None, None, None
        k_list = [50.0] * n
        d_list = [50.0] * n
        for i in range(n, len(cs)):
            cur_h = [x for x in hs[i-n+1:i+1] if x is not None]
            cur_l = [x for x in ls[i-n+1:i+1] if x is not None]
            Hn = max(cur_h) if cur_h else cs[i]
            Ln = min(cur_l) if cur_l else cs[i]
            rsv = (cs[i] - Ln) / (Hn - Ln) * 100 if Hn != Ln else 50
            k = 2.0/3 * k_list[-1] + 1.0/3 * rsv
            d = 2.0/3 * d_list[-1] + 1.0/3 * k
            k_list.append(k); d_list.append(d)
        j_list = [3*k_list[i] - 2*d_list[i] for i in range(len(k_list))]
        return k_list[-1], d_list[-1], j_list[-1]

    k_t, d_t, j_t = calc_kdj(highs, lows, closes)
    k_5d, d_5d, _ = calc_kdj(highs[:-1], lows[:-1], closes[:-1]) if len(closes) > 1 else (None, None, None)

    # ─── 布林线 ───────────────────────────────────────────────
    def calc_boll(close_series, period=20, mult=2):
        cs = close_series
        if len(cs) < period:
            return None, None, None
        recent = cs[-period:]
        mid = sum(recent) / period
        std = math.sqrt(sum((x - mid)**2 for x in recent) / period)
        upper = mid + mult * std
        lower = mid - mult * std
        return upper, mid, lower

    boll_upper, boll_mid, boll_lower = calc_boll(closes)
    price_above_boll_mid = (boll_mid is not None and today_close > boll_mid)

    # ─── 量价分析 ─────────────────────────────────────────────
    # 统计近10日上涨/下跌日的平均成交量
    up_vols = [vols[i] for i in range(len(pcts)) if i >= len(pcts)-10 and pcts[i] > 0]
    dn_vols = [vols[i] for i in range(len(pcts)) if i >= len(pcts)-10 and pcts[i] < 0]
    avg_vol_up = sum(up_vols)/len(up_vols) if up_vols else 0
    avg_vol_dn = sum(dn_vols)/len(dn_vols) if dn_vols else 0
    vol_healthy = avg_vol_up > avg_vol_dn  # 涨时量多，跌时量少

    # 恐慌性放量长阴（近10日跌幅>5%且放量>2倍均量）
    has_panic = any(
        pcts[i] < -5 and vols[i] > _avg(vols, 20) * 2
        for i in range(max(0, N-10), N)
    )

    # 量能从地量温和放大
    vol_20_avg = _avg(vols, 20) or 1
    vol_5_avg  = _avg(vols, 5) or 0
    vol_gradual = vol_5_avg >= vol_20_avg * 0.8 and vol_5_avg <= vol_20_avg * 3

    # ─── 止跌企稳 ─────────────────────────────────────────────
    # 近10日未创60日新低
    low_60d  = _min(lows, 60) or float('inf')
    low_10d  = _min(lows[-10:], 10) if len(lows) >= 10 else low_60d
    no_new_low = low_10d > low_60d * 0.98  # 允许极小误差

    # 波动收窄：近5日振幅 vs 前5日振幅
    def avg_range(n):
        rngs = []
        for i in range(len(highs)-n, len(highs)):
            if highs[i] and lows[i]:
                rngs.append((highs[i] - lows[i]) / highs[i])
        return sum(rngs)/len(rngs) if rngs else None
    range_5d  = avg_range(5)
    range_10d = avg_range(10)
    range_shrink = (range_5d is not None and range_10d is not None
                    and range_5d < range_10d)

    # 无连续大跌（近10日最大单日跌幅<5%）
    max_dd_10d = min([pcts[i] for i in range(max(0,N-10), N)] or [0])
    no_consec_drop = max_dd_10d > -5

    # ─── 评分计算 ─────────────────────────────────────────────

    # ── 维度1：趋势结构（20分）─
    d1 = 0
    d1 += 5 if (ma20_t and today_close > ma20_t) else 0
    d1 += 5 if ma20_flat_or_up else 0
    d1 += 5 if ma60_not_down else 0
    d1 += 5 if lows_rising else 0

    # ── 维度2：量价健康度（20分）─
    d2 = 0
    d2 += 10 if vol_healthy else 0
    d2 += 5 if not has_panic else 0
    d2 += 5 if vol_gradual else 0

    # ── 维度3：止跌企稳（20分）─
    d3 = 0
    d3 += 10 if no_new_low else 0
    d3 += 5 if range_shrink else 0
    d3 += 5 if no_consec_drop else 0

    # ── 维度4：技术指标好转（20分）─
    d4 = 0
    # MACD：绿柱缩短 或 底背离 或 金叉
    macd_ok = False
    if macd_golden_cross:
        macd_ok = True
    elif macd_hist_t is not None and macd_hist_1d_ago is not None and macd_hist_2d_ago is not None:
        if macd_hist_t > macd_hist_1d_ago > macd_hist_2d_ago:  # 连续缩短
            macd_ok = True
    d4 += 10 if macd_ok else 0
    # KDJ/RSI从超卖区回升（RSI<40超卖，>40回升中）
    if rsi_t is not None and rsi_5d is not None and rsi_t < 40 and rsi_t > rsi_5d:
        d4 += 5
    elif rsi_t is not None and rsi_t > 40:
        d4 += 3  # 已在正常区
    # 股价在布林中轨以上
    d4 += 5 if price_above_boll_mid else 0

    # ── 维度5：筹码结构（20分）─
    # 注：数据库无筹码分布数据，根据成交量结构估算
    # 量能温和放大+无对倒迹象 → 隐含筹码改善
    d5 = 0
    if vol_gradual and not has_panic:
        d5 += 8  # 量能温和说明持仓稳定
    # 股价站上多条均线 → 持仓成本趋于集中
    ma_count = sum(1 for v in [ma5_t, ma10_t, ma20_t] if v and today_close > v)
    d5 += 6 if ma_count >= 2 else 3 if ma_count == 1 else 0
    # 近10日量能没有异常放大（无大资金出逃）
    d5 += 6 if not has_panic else 0

    # ── 维度6：基本面与风险稳定（20分）─
    # 数据库无公告/事件数据，根据技术面推断
    d6 = 0
    # 无连续跌停/大幅跳空缺口（近10日）
    gaps = []
    for i in range(1, min(10, N)):
        gap = (opens[N-i] - closes[N-i-1]) / closes[N-i-1] if closes[N-i-1] else 0
        gaps.append(gap)
    big_gap_down = any(g < -0.09 for g in gaps)  # >9%向下跳空
    d6 += 7 if not big_gap_down else 0
    # 近10日最大跌幅有限
    d6 += 7 if max_dd_10d > -7 else 0
    # RSI不过低（不是恐慌杀跌）
    d6 += 6 if rsi_t and rsi_t > 25 else 0

    total = d1 + d2 + d3 + d4 + d5 + d6

    # ─── 判断结论 ─────────────────────────────────────────────
    if total >= 80:
        verdict = "极强稳中向好 ✦"
        verdict_color = "#2ecc71"
    elif total >= 60:
        verdict = "温和稳中向好"
        verdict_color = "#27ae60"
    elif total >= 40:
        verdict = "震荡磨底，偏弱"
        verdict_color = "#f39c12"
    else:
        verdict = "仍在弱势 ▦"
        verdict_color = "#e63946"

    # ─── 诊断依据 ─────────────────────────────────────────────
    reasons = []

    # 维度1依据
    r1 = []
    if ma20_t and today_close > ma20_t: r1.append(f"股价({today_close:.2f})>MA20({ma20_t:.2f})")
    else: r1.append(f"股价({today_close:.2f})<MA20({ma20_t:.2f})" if ma20_t else "MA20数据不足")
    r1.append("MA20走平/向上" if ma20_flat_or_up else "MA20下行")
    r1.append("60日线企稳" if ma60_not_down else "60日线仍弱")
    r1.append("低点逐步抬高" if lows_rising else "低点未抬高")
    reasons.append({ "dim": "趋势结构", "score": d1, "max": 20,
                     "items": r1 })

    # 维度2依据
    r2 = []
    r2.append("涨时量多跌时量少" if vol_healthy else "量价配合一般")
    r2.append("无恐慌放量大阴" if not has_panic else "⚠️近10日出现恐慌放量")
    r2.append("量能从低位温和放大" if vol_gradual else "量能不足/异常")
    reasons.append({ "dim": "量价健康度", "score": d2, "max": 20,
                     "items": r2 })

    # 维度3依据
    r3 = []
    r3.append(f"近10日未创60日新低" if no_new_low else "⚠️近10日创60日新低")
    r3.append("波动收窄" if range_shrink else "波动未收窄")
    r3.append("无连续大跌" if no_consec_drop else "⚠️近期有连续大跌")
    reasons.append({ "dim": "止跌企稳", "score": d3, "max": 20,
                     "items": r3 })

    # 维度4依据
    r4 = []
    if macd_golden_cross: r4.append("MACD已金叉✅")
    elif macd_hist_t is not None and macd_hist_t > macd_hist_1d_ago: r4.append("MACD柱连续收短✅")
    else: r4.append("MACD仍弱" if macd_hist_t else "MACD数据不足")
    if rsi_t:
        r4.append(f"RSI={rsi_t:.1f}" + ("超卖" if rsi_t < 40 else "正常" if rsi_t < 70 else "偏高"))
    r4.append("股价>布林中轨" if price_above_boll_mid else "股价<布林中轨")
    reasons.append({ "dim": "技术指标好转", "score": d4, "max": 20,
                     "items": r4 })

    # 维度5依据
    r5 = []
    r5.append("量能温和，持仓稳定" if vol_gradual and not has_panic else "量能结构一般")
    r5.append(f"站上{ma_count}条均线" if ma_count else "均线压力重")
    r5.append("无对倒放量迹象" if not has_panic else "⚠️存在异常放量")
    reasons.append({ "dim": "筹码结构改善", "score": d5, "max": 20,
                     "items": r5 })

    # 维度6依据
    r6 = []
    r6.append("无大幅跳空缺口" if not big_gap_down else "⚠️存在向下跳空缺口")
    r6.append(f"近10日最大跌幅{abs(max_dd_10d):.1f}%" if max_dd_10d else "")
    r6.append(f"RSI={rsi_t:.1f}（非恐慌区）" if rsi_t and rsi_t > 25 else "⚠️RSI偏低")
    reasons.append({ "dim": "基本面与风险", "score": d6, "max": 20,
                     "items": r6 })

    return api_ok({
        "ts_code": ts_code,
        "trade_date": today[0],
        "close": today_close,
        "total_score": total,
        "verdict": verdict,
        "verdict_color": verdict_color,
        "dimensions": reasons,
        # 原始指标供前端展示
        "raw": {
            "ma5": round(ma5_t, 2) if ma5_t else None,
            "ma20": round(ma20_t, 2) if ma20_t else None,
            "ma60": round(ma60_t, 2) if ma60_t else None,
            "dif": round(dif_t, 4) if dif_t else None,
            "dea": round(dea_t, 4) if dea_t else None,
            "macd_hist": round(macd_hist_t, 4) if macd_hist_t else None,
            "rsi": round(rsi_t, 1) if rsi_t else None,
            "k": round(k_t, 1) if k_t else None,
            "d": round(d_t, 1) if d_t else None,
            "boll_upper": round(boll_upper, 2) if boll_upper else None,
            "boll_mid": round(boll_mid, 2) if boll_mid else None,
            "boll_lower": round(boll_lower, 2) if boll_lower else None,
            "vol_ratio": round(today_vol / vol_20_avg, 2) if vol_20_avg else None,
        }
    })
def server_err(e):
    return api_err("服务器内部错误", code=500)


from flask import send_file
@app.route("/")
@app.route("/index.html")
def serve_frontend():
    path = "/root/.openclaw/workspace/stock_frontend.html"
    if os.path.exists(path):
        return send_file(path)
    return "Frontend not found", 500

if __name__ == "__main__":
    print("=" * 55)
    print("  📈 A股数据 API 服务")
    print("  端口: 5003")
    print("  文档: http://139.199.85.133:5003")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
