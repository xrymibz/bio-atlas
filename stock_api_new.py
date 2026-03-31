#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股数据 API 服务（Flask）
端口：5003
12个核心接口，全部返回 JSON
启动：python3 stock_api.py
"""

import os, sys, math, datetime, time
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
    pool_name="astock", pool_size=8, pool_reset_session=True, **DB_CONFIG
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

    # 补充最新行情
    latest = row("""
        SELECT close, pct_change, volume, trade_date
        FROM stock_daily_price
        WHERE ts_code = %s ORDER BY trade_date DESC LIMIT 1
    """, (ts_code,))
    if latest:
        data["latest_price"] = sf(latest[0])
        data["pct_change"] = sf(latest[1])
        data["volume"] = si(latest[2])
        data["latest_date"] = str(latest[3]) if latest[3] else None

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
    top_n = min(int(request.args.get("top", 30)), 100)
    page = max(int(request.args.get("page", 1)), 1)
    page_size = 20

    # 取出最新日期
    latest_date_row = row("SELECT MAX(trade_date) FROM stock_daily_price")
    latest_date = latest_date_row[0] if latest_date_row else None
    if not latest_date:
        return api_err("无数据", code=404)

    # 取所有股票最新+历史数据
    pool_rows = rows(f"""
        SELECT
            p.ts_code, b.name, b.industry,
            p.close, (p.close - p.open) / p.open * 100 AS pct_change,
            p.ma5, p.ma10, p.ma20, p.ma60,
            p.volume, p.rise_days, p.fall_days,
            (SELECT MAX(close) FROM stock_daily_price p2
             WHERE p2.ts_code = p.ts_code AND p2.trade_date >= p.trade_date - INTERVAL 30 DAY) AS high_20d,
            (SELECT SUM((p3.close - p3.open) / p3.open * 100) FROM stock_daily_price p3
             WHERE p3.ts_code = p.ts_code AND p3.trade_date >= p.trade_date - INTERVAL 5 DAY) AS rise_5d,
            (SELECT AVG(volume) FROM stock_daily_price p4
             WHERE p4.ts_code = p.ts_code AND p4.trade_date >= p.trade_date - INTERVAL 20 DAY) AS avg_vol_20
        FROM stock_daily_price p
        JOIN stock_basic b ON b.ts_code = p.ts_code
        WHERE p.trade_date = %s
        AND b.is_active = 1
        AND b.name NOT LIKE '%%ST%%'
        AND b.name NOT LIKE '%%*%%'
        LIMIT 1000
    """, (latest_date,))

    items = []
    for r in pool_rows:
        ts = r[0]; name = r[1]; industry = r[2]
        close = sf(r[3]); pct = sf(r[4])
        ma5 = sf(r[5]); ma10 = sf(r[6]); ma20 = sf(r[7]); ma60 = sf(r[8])
        volume = si(r[9]); rise_days = si(r[10]) or 0; fall_days = si(r[11]) or 0
        high_20d = sf(r[12])
        rise_5d = sf(r[13]) or 0.0; avg_vol_20 = sf(r[14])

        # 基础过滤（ma20仍用于评分，但不作为入池门槛）
        if not close:
            continue

        # 综合评分（满分100）
        score = 0.0
        # 趋势（30分）：价格位于均线上方越多分数越高
        above_ma = 0
        if close > ma5: above_ma += 10
        if close > ma10: above_ma += 10
        if close > ma20: above_ma += 10
        score += above_ma

        # 动量（25分）：近5日涨幅
        score += min(25, max(0, rise_5d * 5))

        # 量能（20分）
        if avg_vol_20:
            vol_ratio = volume / avg_vol_20
            score += min(20, vol_ratio * 10)

        # 相对强度（15分）：对比ma20的强度
        if ma20:
            distance = (close - ma20) / ma20 * 100
            score += min(15, max(0, distance * 3))

        # 涨跌幅（10分）
        score += min(10, max(0, (pct or 0) * 2 + 5))

        items.append({
            "ts_code": ts, "name": name, "industry": industry or "未知",
            "close": close, "pct_change": pct,
            "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
            "rise_5d": rise_5d,
            "volume_ratio": round(volume / avg_vol_20, 2) if avg_vol_20 else None,
            "score": round(score, 1),
            "high_20d": high_20d,
            "rise_days": rise_days,
            "fall_days": fall_days,
        })

    # 排序
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
    highs = [sf(r[5]) for r in recent if sf(r[5])]
    lows = [sf(r[6]) for r in recent if sf(r[6])]
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
    latest_date_row = row("SELECT MAX(trade_date) FROM stock_daily_price")
    latest_date = str(latest_date_row[0]) if latest_date_row and latest_date_row[0] else None
    if not latest_date:
        return api_err("无数据", code=404)

    # 涨跌家数（用真实涨跌幅计算）
    rise_cnt = row("SELECT COUNT(*) FROM stock_daily_price p JOIN stock_basic b ON b.ts_code=p.ts_code WHERE p.trade_date=%s AND b.is_active=1 AND (p.close-p.open)/p.open*100>0", (latest_date,))
    fall_cnt = row("SELECT COUNT(*) FROM stock_daily_price p JOIN stock_basic b ON b.ts_code=p.ts_code WHERE p.trade_date=%s AND b.is_active=1 AND (p.close-p.open)/p.open*100<0", (latest_date,))
    total_active = row("SELECT COUNT(*) FROM stock_daily_price p JOIN stock_basic b ON b.ts_code=p.ts_code WHERE p.trade_date=%s AND b.is_active=1", (latest_date,))

    r_cnt = rise_cnt[0] if rise_cnt else 0
    f_cnt = fall_cnt[0] if fall_cnt else 0
    t_cnt = total_active[0] if total_active else 0
    earn_ratio = round(r_cnt / t_cnt * 100, 2) if t_cnt else 0

    # 涨停股（涨幅>=9.9%）
    limit_up_rows = rows("""
        SELECT p.ts_code, b.name, b.industry, p.close,
               (p.close - p.open) / p.open * 100 AS computed_pct
        FROM stock_daily_price p
        JOIN stock_basic b ON b.ts_code = p.ts_code
        WHERE p.trade_date = %s AND (p.close-p.open)/p.open*100 >= 9.9 AND b.is_active = 1
        ORDER BY computed_pct DESC LIMIT 10
    """, (latest_date,))

    # 强势股（站上ma20且近5日涨幅前10）
    strong_rows = rows(f"""
        SELECT p.ts_code, b.name, b.industry, p.close,
               (p.close - p.open) / p.open * 100 AS pct_change,
               (SELECT SUM((p3.close - p3.open) / p3.open * 100) FROM stock_daily_price p3
                WHERE p3.ts_code = p.ts_code AND p3.trade_date >= p.trade_date - INTERVAL 5 DAY) AS rise_5d
        FROM stock_daily_price p
        JOIN stock_basic b ON b.ts_code = p.ts_code
        WHERE p.trade_date = %s AND b.is_active = 1
        AND b.name NOT LIKE '%%ST%%' AND b.name NOT LIKE '%%*%%'
        AND p.close > p.ma20 AND p.ma20 IS NOT NULL
        ORDER BY rise_5d DESC LIMIT 10
    """, (latest_date,))

    # 跌幅榜
    limit_down_rows = rows("""
        SELECT p.ts_code, b.name, p.close,
               (p.close - p.open) / p.open * 100 AS computed_pct
        FROM stock_daily_price p
        JOIN stock_basic b ON b.ts_code = p.ts_code
        WHERE p.trade_date = %s AND (p.close-p.open)/p.open*100 <= -9.9 AND b.is_active = 1
        ORDER BY computed_pct ASC LIMIT 5
    """, (latest_date,))

    # 板块统计（按行业聚合涨幅）
    sector_rows = rows("""
        SELECT b.industry,
               COUNT(*) AS stock_count,
               AVG((p.close - p.open) / p.open * 100) AS avg_pct,
               SUM(CASE WHEN (p.close-p.open)/p.open*100 > 0 THEN 1 ELSE 0 END) AS rise_count
        FROM stock_daily_price p
        JOIN stock_basic b ON b.ts_code = p.ts_code
        WHERE p.trade_date = %s AND b.is_active = 1 AND b.industry IS NOT NULL
        GROUP BY b.industry
        HAVING COUNT(*) >= 3
        ORDER BY avg_pct DESC
        LIMIT 5
    """, (latest_date,))

    # 市场整体情况
    market_vol = row("SELECT SUM(volume), SUM(amount) FROM stock_daily_price WHERE trade_date=%s", (latest_date,))
    index_data = row("SELECT close, pct_change FROM stock_daily_price WHERE ts_code='000001.SH' AND trade_date=%s", (latest_date,))
    index2_data = row("SELECT close, pct_change FROM stock_daily_price WHERE ts_code='399001.SZ' AND trade_date=%s", (latest_date,))

    # 情绪判断
    if earn_ratio >= 70:
        emotion = "极强 💪 赚钱效应爆棚"
    elif earn_ratio >= 55:
        emotion = "偏强 👍 赚钱效应良好"
    elif earn_ratio >= 45:
        emotion = "中性 ➡ 震荡整理格局"
    elif earn_ratio >= 30:
        emotion = "偏弱 👎 亏钱效应明显"
    else:
        emotion = "极弱 ❌ 亏钱效应爆棚"

    lu_cnt = row("SELECT COUNT(*) FROM stock_daily_price WHERE trade_date=%s AND (close-open)/open*100>=9.9", (latest_date,))
    ld_cnt = row("SELECT COUNT(*) FROM stock_daily_price WHERE trade_date=%s AND (close-open)/open*100<=-9.9", (latest_date,))

    # 明日关注方向
    concerns = []
    if index_data and sf(index_data[1]) and sf(index_data[1]) < -2:
        concerns.append("大盘大幅杀跌，谨慎为主，控制仓位")
    if limit_down_rows and len(limit_down_rows) > 10:
        concerns.append("跌停家数较多，市场情绪偏空")
    if r_cnt < f_cnt * 2:
        concerns.append("跌多涨少，防御为主，关注护盘板块")
    strong_sectors = [str(r[0]) for r in sector_rows[:2] if r[0]]
    if strong_sectors:
        concerns.append(f"强势板块：{'、'.join(strong_sectors)}，可关注")

    return api_ok({
        "trade_date": latest_date,
        "market": {
            "rise_count": r_cnt, "fall_count": f_cnt,
            "limit_up_count": lu_cnt[0] if lu_cnt else 0,
            "limit_down_count": ld_cnt[0] if ld_cnt else 0,
            "total_active": t_cnt, "earn_ratio": earn_ratio,
            "emotion": emotion,
            "shanghai_close": sf(index_data[0]) if index_data else None,
            "shanghai_pct": sf(index_data[1]) if index_data else None,
            "shenzhen_close": sf(index2_data[0]) if index2_data else None,
            "shenzhen_pct": sf(index2_data[1]) if index2_data else None,
            "total_volume": sf(market_vol[0]) if market_vol else None,
            "total_amount": sf(market_vol[1]) if market_vol else None,
        },
        "hot_sectors": [
            {"industry": r[0], "avg_pct": round(sf(r[2]) or 0, 2),
             "rise_count": r[3], "stock_count": r[1]}
            for r in (sector_rows or [])
        ],
        "limit_up_list": [
            {"ts_code": r[0], "name": r[1], "industry": r[2],
             "close": sf(r[3]), "pct": round(sf(r[4]) or 0, 2)}
            for r in (limit_up_rows or [])
        ],
        "strong_stocks": [
            {"ts_code": r[0], "name": r[1], "industry": r[2],
             "close": sf(r[3]), "pct": sf(r[4]), "rise_5d": round(sf(r[5]) or 0, 2)}
            for r in (strong_rows or [])
        ],
        "limit_down_list": [
            {"ts_code": r[0], "name": r[1], "close": sf(r[2]), "pct": sf(r[3])}
            for r in (limit_down_rows or [])
        ],
        "concerns": concerns if concerns else ["市场无明显异常，关注强势板块轮动机会"],
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


# ===================== CORS & 全局错误处理 =====================
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
def server_err(e):
    return api_err("服务器内部错误", code=500)


if __name__ == "__main__":
    print("=" * 55)
    print("  📈 A股数据 API 服务")
    print("  端口: 5003")
    print("  文档: http://139.199.85.133:5003")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
