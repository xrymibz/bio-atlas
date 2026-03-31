#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股数据服务 - 统一Flask版（端口5001）
前端Web界面 + 12个REST API
"""
import os, math, datetime, json, warnings
from functools import wraps
from flask import Flask, request, jsonify, send_file
warnings.filterwarnings("ignore")

app = Flask(__name__, static_folder=None)
app.config["JSON_AS_ASCII"] = False

DB = {
    "host": "localhost", "user": "root",
    "password": "OpenClaw@2026", "database": "a_stock_data"
}

# ====================== 工具函数 ======================
def ok(data=None, msg="success"):
    return jsonify({"code": 0, "msg": msg, "data": data})

def er(msg="error", code=1):
    return jsonify({"code": code, "msg": msg})

def req(*names):
    def d(f):
        @wraps(f)
        def ff(*args, **kwargs):
            miss = [n for n in names if not request.args.get(n)]
            if miss: return er(f"缺少参数: {', '.join(miss)}", 400)
            return f(*args, **kwargs)
        return ff
    return d

import mysql.connector
from mysql.connector import pooling
cnx = pooling.MySQLConnectionPool(pool_name="apool", pool_size=8, pool_reset_session=True, **DB)

def db():
    return cnx.get_connection()

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

def qr(sql, args=None, one=False):
    c = db()
    cur = c.cursor()
    cur.execute(sql, args or ())
    r = cur.fetchone() if one else cur.fetchall()
    cur.close(); c.close()
    return r

def lvl(s):
    return ("强烈推荐" if s >= 80 else "值得关注" if s >= 65 else
            "中性" if s >= 50 else "谨慎" if s >= 35 else "回避")

# ====================== 指标计算 ======================
def rsi(closes, p=14):
    if len(closes) < p+1: return None
    g = [max(closes[i]-closes[i-1], 0) for i in range(1, len(closes))]
    l = [abs(min(closes[i]-closes[i-1], 0)) for i in range(1, len(closes))]
    ag = sum(g[-p:]) / p
    al = sum(l[-p:]) / p
    return round(100-100/(1+ag/al), 4) if al else 100.0

def calc_ema(data, n):
    if len(data) < n: return None
    k = 2.0/(n+1)
    v = sum(data[:n]) / n
    for x in data[n:]: v = x*k + v*(1-k)
    return v

def macd(closes, f=12, s=26, sig=9):
    if len(closes) < s+sig: return None, None, None
    difs = []
    for i in range(s-1, len(closes)):
        ef = calc_ema(closes[:i+1], f)
        es = calc_ema(closes[:i+1], s)
        if ef and es: difs.append(ef - es)
    if len(difs) < sig: return None, None, None
    dif = round(difs[-1], 4)
    dea = round(calc_ema(difs, sig), 4)
    return dif, dea, round((dif-dea)*2, 4)

def kdj(h, l, c, n=9):
    if len(c) < n: return None, None, None
    rsv = []
    for i in range(n-1, len(c)):
        hh, ll = max(h[i-n+1:i+1]), min(l[i-n+1:i+1])
        rsv.append((c[i]-ll)/(hh-ll)*100 if hh!=ll else 50)
    k = d = 50.0
    for r in rsv:
        k = (2*k+r)/3; d = (2*d+k)/3
    return round(k,4), round(d,4), round(3*k-2*d,4)

def boll(closes, n=20, k=2):
    if len(closes) < n: return None, None, None
    ma = sum(closes[-n:])/n
    std = math.sqrt(sum((x-ma)**2 for x in closes[-n:])/n)
    return round(ma+k*std, 3), round(ma, 3), round(ma-k*std, 3)

def indicators(klines):
    cs = [x["close"] for x in klines if x.get("close") is not None]
    hs = [x["high"] for x in klines if x.get("high") is not None]
    ls = [x["low"] for x in klines if x.get("low") is not None]
    vs = [x["volume"] for x in klines if x.get("volume") is not None]
    n = len(cs)
    r = {}
    r["ma5"]  = round(sum(cs[-5:])/min(5,n), 3)  if n>=5 else None
    r["ma10"] = round(sum(cs[-10:])/min(10,n), 3) if n>=10 else None
    r["ma20"] = round(sum(cs[-20:])/min(20,n), 3) if n>=20 else None
    r["ma60"] = round(sum(cs[-60:])/min(60,n), 3) if n>=60 else None
    r["ma120"]= round(sum(cs[-120:])/min(120,n),3) if n>=120 else None
    r["ma250"]= round(sum(cs[-250:])/min(250,n),3) if n>=250 else None
    d1,d2,d3 = macd(cs); r["dif"]=d1; r["dea"]=d2; r["macd"]=d3
    r["rsi_6"]  = rsi(cs, 6)
    r["rsi_12"] = rsi(cs, 12)
    r["rsi_24"] = rsi(cs, 24)
    b1,b2,b3 = boll(cs); r["boll_upper"]=b1; r["boll_mid"]=b2; r["boll_lower"]=b3
    if len(hs)>=9 and len(ls)>=9:
        k1,k2,k3 = kdj(hs, ls, cs); r["kdj_k"]=k1; r["kdj_d"]=k2; r["kdj_j"]=k3
    prev = cs[-2] if len(cs)>=2 else None
    if prev and hs: r["swing"] = round((max(hs)-min(ls))/prev*100, 4)
    if vs and len(vs)>=6:
        avg5 = sum(vs[-6:-1])/5
        r["volume_ratio"] = round(vs[-1]/avg5, 4) if avg5 else None
    return r

def pct_c(open_p, close_p):
    if open_p and open_p != 0 and close_p: return round((close_p-open_p)/open_p*100, 4)
    return 0.0

# ====================== 首页 ======================
@app.route("/")
@app.route("/index.html")
def index():
    p = "/root/.openclaw/workspace/stock_frontend.html"
    return send_file(p) if os.path.exists(p) else er("前端文件未找到", 500)

# ====================== 1. 股票基础信息 ======================
@app.route("/api/stock/info")
@req("ts_code")
def stock_info():
    ts = request.args.get("ts_code","").strip()
    r = qr("""
        SELECT ts_code,symbol,name,industry,sub_industry,market,
               list_date,is_active,created_at,updated_at
        FROM stock_basic WHERE ts_code=%s
    """, (ts,), one=True)
    if not r: return er("股票不存在", 404)
    fs = ["ts_code","symbol","name","industry","sub_industry","market","list_date","is_active","created_at","updated_at"]
    d = {f: (str(v) if v is not None else None) for f,v in zip(fs, r)}
    lr = qr("SELECT close,(close-open)/open*100,volume,trade_date FROM stock_daily_price WHERE ts_code=%s ORDER BY trade_date DESC LIMIT 1", (ts,), one=True)
    if lr:
        d["latest_price"] = sf(lr[0])
        d["pct_change"] = round(sf(lr[1]) if lr[1] else 0.0, 2)
        d["volume"] = si(lr[2])
        d["latest_date"] = str(lr[3]) if lr[3] else None
    return ok(d)

# ====================== 2. 日线行情 ======================
@app.route("/api/stock/daily")
@req("ts_code")
def stock_daily():
    ts = request.args.get("ts_code","").strip()
    days = min(int(request.args.get("days", 60)), 500)
    page = max(int(request.args.get("page", 1)), 1)
    ps = min(int(request.args.get("page_size", 100)), 500)
    off = (page-1)*ps
    total = qr("SELECT COUNT(*) FROM stock_daily_price WHERE ts_code=%s", (ts,), one=True)
    tot = total[0] if total else 0
    rs = qr("""
        SELECT trade_date,open,close,high,low,volume,amount,
               ma5,ma10,ma20,ma60,ma120,ma250,
               support_1,support_2,support_3,pressure_1,pressure_2,pressure_3,
               break_ma5,break_ma10,break_ma20,break_ma60,
               rise_days,fall_days,rise_total_pct,fall_total_pct
        FROM stock_daily_price WHERE ts_code=%s
        ORDER BY trade_date DESC LIMIT %s OFFSET %s
    """, (ts, ps, off))
    items = []
    for r in rs:
        op, cl = sf(r[1]), sf(r[2])
        pc = pct_c(r[1], r[2])
        items.append({
            "trade_date": str(r[0]) if r[0] else None,
            "open": op, "close": cl, "high": sf(r[3]), "low": sf(r[4]),
            "volume": si(r[5]), "amount": sf(r[6]),
            "pct_change": round(pc, 2),
            "ma5": sf(r[7]), "ma10": sf(r[8]), "ma20": sf(r[9]),
            "ma60": sf(r[10]), "ma120": sf(r[11]), "ma250": sf(r[12]),
            "support_1": sf(r[13]), "support_2": sf(r[14]), "support_3": sf(r[15]),
            "pressure_1": sf(r[16]), "pressure_2": sf(r[17]), "pressure_3": sf(r[18]),
            "break_ma5": r[19], "break_ma10": r[20], "break_ma20": r[21], "break_ma60": r[22],
            "rise_days": r[23], "fall_days": r[24],
            "rise_total_pct": sf(r[25]), "fall_total_pct": sf(r[26]),
        })
    return ok({"ts_code": ts, "total": tot, "page": page, "page_size": ps,
               "pages": (tot+ps-1)//ps if ps else 1, "items": items})

# ====================== 3. 技术指标 ======================
@app.route("/api/stock/indicator")
@req("ts_code")
def stock_indicator():
    ts = request.args.get("ts_code","").strip()
    days = min(int(request.args.get("days", 60)), 500)
    # 优先指标表
    ir = qr("""
        SELECT trade_date,ma5,ma10,ma20,ma60,ma120,ma250,
               dif,dea,macd,rsi_6,rsi_12,rsi_24,
               boll_upper,boll_mid,boll_lower,
               kdj_k,kdj_d,kdj_j,swing,turnover_rate,volume_ratio
        FROM stock_daily_price_indicator WHERE ts_code=%s
        ORDER BY trade_date DESC LIMIT %s
    """, (ts, days))
    if ir:
        items = [{"trade_date": str(x[0]) if x[0] else None,
                  "ma5":sf(x[1]),"ma10":sf(x[2]),"ma20":sf(x[3]),"ma60":sf(x[4]),
                  "ma120":sf(x[5]),"ma250":sf(x[6]),
                  "dif":sf(x[7]),"dea":sf(x[8]),"macd":sf(x[9]),
                  "rsi_6":sf(x[10]),"rsi_12":sf(x[11]),"rsi_24":sf(x[12]),
                  "boll_upper":sf(x[13]),"boll_mid":sf(x[14]),"boll_lower":sf(x[15]),
                  "kdj_k":sf(x[16]),"kdj_d":sf(x[17]),"kdj_j":sf(x[18]),
                  "swing":sf(x[19]),"turnover_rate":sf(x[20]),"volume_ratio":sf(x[21])}
                 for x in ir]
        return ok({"source": "table", "items": items})
    # 实时计算
    pr = qr("""
        SELECT trade_date,open,close,high,low,volume,amount
        FROM stock_daily_price WHERE ts_code=%s
        ORDER BY trade_date ASC LIMIT %s
    """, (ts, max(min(days, 300), 300)))
    if not pr: return er("无数据", 404)
    items = []
    for i in range(20, len(pr)+1):
        kl = [{"date": str(pr[j][0]), "open": sf(pr[j][1]), "close": sf(pr[j][2]),
               "high": sf(pr[j][3]), "low": sf(pr[j][4]), "volume": si(pr[j][5])}
              for j in range(i)]
        ind = indicators(kl)
        if ind:
            ind["trade_date"] = str(pr[i-1][0])
            ind["open"] = sf(pr[i-1][1])
            ind["close"] = sf(pr[i-1][2])
            ind["volume"] = si(pr[i-1][5])
            items.append(ind)
    items.reverse()
    return ok({"source": "computed", "items": items[-days:]})

# ====================== 4. 资金数据 ======================
@app.route("/api/stock/capital")
@req("ts_code")
def stock_capital():
    ts = request.args.get("ts_code","").strip()
    days = min(int(request.args.get("days", 30)), 500)
    rs = qr("""
        SELECT trade_date,main_inflow,super_inflow,big_inflow,mid_inflow,small_inflow,
               north_money,north_hold,margin,margin_change
        FROM stock_daily_capital WHERE ts_code=%s
        ORDER BY trade_date DESC LIMIT %s
    """, (ts, days))
    if not rs:
        return ok({"source": "table", "items": [],
                   "note": "资金数据需东方财富收费接口，免费数据源暂无"})
    items = [{"trade_date": str(x[0]),
             "main_inflow": sf(x[1]), "super_inflow": sf(x[2]), "big_inflow": sf(x[3]),
             "mid_inflow": sf(x[4]), "small_inflow": sf(x[5]),
             "north_money": sf(x[6]), "north_hold": sf(x[7]),
             "margin": sf(x[8]), "margin_change": sf(x[9])}
            for x in rs]
    return ok({"source": "table", "items": items})

# ====================== 5. 筹码分布 ======================
@app.route("/api/stock/chip")
@req("ts_code")
def stock_chip():
    ts = request.args.get("ts_code","").strip()
    days = min(int(request.args.get("days", 30)), 500)
    rs = qr("""
        SELECT trade_date,avg_cost,concentration,
               chip_70_low,chip_70_up,chip_90_low,chip_90_up,profit_ratio
        FROM stock_chip_distribution WHERE ts_code=%s
        ORDER BY trade_date DESC LIMIT %s
    """, (ts, days))
    if rs:
        items = [{"trade_date": str(x[0]),
                 "avg_cost": sf(x[1]), "concentration": sf(x[2]),
                 "chip_70_low": sf(x[3]), "chip_70_up": sf(x[4]),
                 "chip_90_low": sf(x[5]), "chip_90_up": sf(x[6]),
                 "profit_ratio": sf(x[7])} for x in rs]
        return ok({"source": "table", "items": items})
    pr = qr("""
        SELECT trade_date,close,volume FROM stock_daily_price
        WHERE ts_code=%s ORDER BY trade_date DESC LIMIT %s
    """, (ts, min(days, 30)))
    if not pr: return er("无数据", 404)
    items = []
    for r in pr:
        c = sf(r[1]); v = si(r[2])
        if c and v:
            items.append({"trade_date": str(r[0]),
                          "avg_cost": round(c*0.95, 2),
                          "concentration": round(v/10000000, 4) if v else None,
                          "chip_70_low": round(c*0.92, 2),
                          "chip_70_up": round(c*1.08, 2),
                          "chip_90_low": round(c*0.88, 2),
                          "chip_90_up": round(c*1.12, 2),
                          "profit_ratio": round((c-c*0.95)/c*100, 2),
                          "_note": "（价格估算）"})
    return ok({"source": "estimated", "items": items})

# ====================== 6. 每日事件 ======================
@app.route("/api/stock/events")
@req("ts_code")
def stock_events():
    ts = request.args.get("ts_code","").strip()
    days = min(int(request.args.get("days", 30)), 500)
    rs = qr("""
        SELECT trade_date,is_limit_up,is_limit_down,is_break_ma20,is_break_ma60,
               is_high_1y,is_low_1y,is_unlock_day,unlock_ratio
        FROM stock_daily_events WHERE ts_code=%s
        ORDER BY trade_date DESC LIMIT %s
    """, (ts, days))
    if rs:
        items = [{"trade_date": str(x[0]),
                 "is_limit_up": x[1], "is_limit_down": x[2],
                 "is_break_ma20": x[3], "is_break_ma60": x[4],
                 "is_high_1y": x[5], "is_low_1y": x[6],
                 "is_unlock_day": x[7], "unlock_ratio": sf(x[8])}
                for x in rs]
        return ok({"source": "table", "items": items})
    pr = qr("""
        SELECT trade_date,open,close,ma20,ma60 FROM stock_daily_price
        WHERE ts_code=%s ORDER BY trade_date DESC LIMIT %s
    """, (ts, min(days, 365)))
    if not pr: return er("无数据", 404)
    items = []
    for r in pr:
        op = sf(r[1]); cl = sf(r[2])
        pc = pct_c(r[1], r[2])
        items.append({"trade_date": str(r[0]),
                      "is_limit_up": 1 if pc >= 9.9 else 0,
                      "is_limit_down": 1 if pc <= -9.9 else 0,
                      "is_break_ma20": 1 if sf(r[3]) and cl and cl < sf(r[3]) else 0,
                      "is_break_ma60": 1 if sf(r[4]) and cl and cl < sf(r[4]) else 0,
                      "is_high_1y": 0, "is_low_1y": 0,
                      "is_unlock_day": 0, "unlock_ratio": None})
    items.reverse()
    return ok({"source": "computed", "items": items[-days:]})

# ====================== 7. 基本面估值 ======================
@app.route("/api/stock/funda")
@req("ts_code")
def stock_funda():
    ts = request.args.get("ts_code","").strip()
    days = min(int(request.args.get("days", 30)), 500)
    rs = qr("""
        SELECT trade_date,pe_ttm,pb_mrq,ps_ttm,dividend_yield,
               total_share,float_share,market_cap,float_cap,holder_num,holder_change
        FROM stock_daily_funda WHERE ts_code=%s
        ORDER BY trade_date DESC LIMIT %s
    """, (ts, days))
    if rs:
        items = [{"trade_date": str(x[0]),
                 "pe_ttm": sf(x[1]), "pb_mrq": sf(x[2]), "ps_ttm": sf(x[3]),
                 "dividend_yield": sf(x[4]),
                 "total_share": sf(x[5]), "float_share": sf(x[6]),
                 "market_cap": sf(x[7]), "float_cap": sf(x[8]),
                 "holder_num": si(x[9]), "holder_change": sf(x[10])}
                for x in rs]
        return ok({"source": "table", "items": items})
    lp = qr("SELECT close FROM stock_daily_price WHERE ts_code=%s ORDER BY trade_date DESC LIMIT 1", (ts,), one=True)
    price = sf(lp[0]) if lp else None
    pr = qr("SELECT trade_date FROM stock_daily_price WHERE ts_code=%s ORDER BY trade_date DESC LIMIT %s", (ts, min(days, 30)))
    if pr:
        items = [{"trade_date": str(r[0]),
                 "pe_ttm": None, "pb_mrq": None, "ps_ttm": None, "dividend_yield": None,
                 "total_share": None, "float_share": None,
                 "market_cap": round(price*100000000, 2) if price else None,
                 "float_cap": round(price*80000000, 2) if price else None,
                 "holder_num": None, "holder_change": None,
                 "_note": "（市值估算，精确数据需收费接口）"} for r in pr]
        return ok({"source": "estimated", "items": items})
    return er("无数据", 404)

# ====================== 8. 市场概况 ======================
@app.route("/api/market/overview")
def market_overview():
    ld = qr("SELECT MAX(trade_date) FROM stock_daily_price", one=True)
    latest = str(ld[0]) if ld and ld[0] else None
    if not latest: return er("无数据", 404)
    r1 = qr("SELECT COUNT(*) FROM stock_daily_price p JOIN stock_basic b ON b.ts_code=p.ts_code WHERE p.trade_date=%s AND b.is_active=1 AND (p.close-p.open)/p.open*100>0", (latest,), one=True)
    r2 = qr("SELECT COUNT(*) FROM stock_daily_price p JOIN stock_basic b ON b.ts_code=p.ts_code WHERE p.trade_date=%s AND b.is_active=1 AND (p.close-p.open)/p.open*100<0", (latest,), one=True)
    rc = qr("SELECT COUNT(*) FROM stock_daily_price p JOIN stock_basic b ON b.ts_code=p.ts_code WHERE p.trade_date=%s AND b.is_active=1", (latest,), one=True)
    r3 = qr("SELECT COUNT(*) FROM stock_daily_price WHERE trade_date=%s AND (close-open)/open*100>=9.9", (latest,), one=True)
    r4 = qr("SELECT COUNT(*) FROM stock_daily_price WHERE trade_date=%s AND (close-open)/open*100<=-9.9", (latest,), one=True)
    rv = qr("SELECT SUM(volume),SUM(amount) FROM stock_daily_price WHERE trade_date=%s", (latest,), one=True)
    ri = qr("SELECT close,(close-open)/open*100 FROM stock_daily_price WHERE ts_code='000001.SH' AND trade_date=%s", (latest,), one=True)
    r_cnt = r1[0] if r1 else 0
    f_cnt = r2[0] if r2 else 0
    t_cnt = rc[0] if rc else 0
    earn = round(r_cnt/(r_cnt+f_cnt)*100, 2) if (r_cnt+f_cnt) > 0 else 0
    return ok({"source": "computed", "data": {
        "trade_date": latest,
        "rise_count": r_cnt, "fall_count": f_cnt,
        "limit_up_count": r3[0] if r3 else 0,
        "limit_down_count": r4[0] if r4 else 0,
        "total_volume": sf(rv[0]) if rv else None,
        "total_amount": sf(rv[1]) if rv else None,
        "index_close": sf(ri[0]) if ri else None,
        "index_pct": round(sf(ri[1]) if ri else 0, 2),
        "earn_ratio": earn, "total_stocks": t_cnt
    }})

# ====================== 9. 强势股池 ======================
@app.route("/api/strategy/pool")
def strategy_pool():
    page = max(int(request.args.get("page", 1)), 1)
    ps = 20
    ld = qr("SELECT MAX(trade_date) FROM stock_daily_price", one=True)
    latest = str(ld[0]) if ld and ld[0] else None
    if not latest: return er("无数据", 404)
    rows = qr(f"""
        SELECT p.ts_code,b.name,b.industry,p.close,
               (p.close-p.open)/p.open*100 AS pct,
               p.ma5,p.ma10,p.ma20,p.ma60,p.volume,
               (SELECT MAX(close) FROM stock_daily_price p2
                WHERE p2.ts_code=p.ts_code AND p2.trade_date>=p.trade_date-INTERVAL 30 DAY) AS h20d,
               (SELECT SUM((p3.close-p3.open)/p3.open*100) FROM stock_daily_price p3
                WHERE p3.ts_code=p.ts_code AND p3.trade_date>=p.trade_date-INTERVAL 5 DAY) AS r5d,
               (SELECT AVG(volume) FROM stock_daily_price p4
                WHERE p4.ts_code=p.ts_code AND p4.trade_date>=p.trade_date-INTERVAL 20 DAY) AS avol
        FROM stock_daily_price p
        JOIN stock_basic b ON b.ts_code=p.ts_code
        WHERE p.trade_date=%s AND b.is_active=1
        AND b.name NOT LIKE '%%ST%%' AND b.name NOT LIKE '%%*%%'
        AND p.close>p.ma20 AND p.ma20 IS NOT NULL
        LIMIT 1000
    """, (latest,))
    items = []
    for r in (rows or []):
        ts, name, ind = r[0], r[1], r[2]
        close = sf(r[3]); pct = round(sf(r[4]) if r[4] else 0.0, 2)
        ma5, ma10, ma20, ma60 = sf(r[5]), sf(r[6]), sf(r[7]), sf(r[8])
        vol = si(r[9]); h20 = sf(r[10]); r5 = sf(r[11]) or 0.0; avol = sf(r[12])
        if not close or not ma20 or r5 <= 0: continue
        if avol and vol and vol < avol: continue
        sc = 0.0
        if ma5 and close > ma5: sc += 10
        if ma10 and close > ma10: sc += 10
        if close > ma20: sc += 10
        sc += min(25, max(0, r5*5))
        if avol: sc += min(20, (vol/avol)*10)
        if ma20: sc += min(15, max(0, (close-ma20)/ma20*100*3))
        sc += min(10, max(0, pct*2+5))
        items.append({"ts_code": ts, "name": name, "industry": ind or "未知",
                      "close": close, "pct_change": pct,
                      "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
                      "rise_5d": round(r5, 2),
                      "volume_ratio": round(vol/avol, 2) if avol else None,
                      "score": round(sc, 1), "high_20d": h20})
    items.sort(key=lambda x: -x["score"])
    total = len(items); start = (page-1)*ps
    return ok({"total": total, "page": page, "page_size": ps,
               "strategy": "站上20日线+近5日涨幅+放量",
               "items": items[start:start+ps]})

# ====================== 10. 趋势判断 ======================
@app.route("/api/strategy/trend")
@req("ts_code")
def strategy_trend():
    ts = request.args.get("ts_code","").strip()
    days = int(request.args.get("days", 60))
    rows = qr("""
        SELECT trade_date,open,close,high,low,ma5,ma10,ma20,ma60,ma120,support_1,pressure_1
        FROM stock_daily_price WHERE ts_code=%s
        ORDER BY trade_date DESC LIMIT %s
    """, (ts, min(days, 120)))
    if not rows or len(rows) < 20: return er("数据不足", 404)
    cl = sf(rows[0][2]); ma5, ma10, ma20, ma60, ma120 = sf(rows[0][5]), sf(rows[0][6]), sf(rows[0][7]), sf(rows[0][8]), sf(rows[0][9])
    s1, p1 = sf(rows[0][10]), sf(rows[0][11])
    trend = ("上升趋势" if ma20 and cl>ma20 and ma60 and cl>ma60 else
             "震荡偏强" if ma20 and cl>ma20 else
             "下降趋势" if ma20 and cl<ma20 else "震荡")
    tlevel = "强" if trend=="上升趋势" else "弱" if trend=="下降趋势" else "中"
    bs = []
    if ma5 and cl<ma5: bs.append("跌破MA5")
    if ma10 and cl<ma10: bs.append("跌破MA10")
    if ma20 and cl<ma20: bs.append("跌破MA20")
    if ma60 and cl<ma60: bs.append("跌破MA60")
    bus = []
    if len(rows) >= 2:
        cl1 = sf(rows[1][2]); ma5p = sf(rows[1][5]); ma20p = sf(rows[1][7]); ma60p = sf(rows[1][8])
        if ma5 and cl>ma5 and ma5p and cl1<=ma5p: bus.append("突破MA5")
        if ma20 and cl>ma20 and ma20p and cl1<=ma20p: bus.append("突破MA20")
        if ma60 and cl>ma60 and ma60p and cl1<=ma60p: bus.append("突破MA60")
    ma_arr = ("多头排列" if ma5 and ma10 and ma20 and ma5>ma10>ma20 else
              "空头排列" if ma5 and ma10 and ma20 and ma5<ma10<ma20 else "混合排列")
    rh = [sf(r[3]) for r in rows[:10] if sf(r[3])]
    rl = [sf(r[4]) for r in rows[:10] if sf(r[4])]
    return ok({"ts_code": ts, "trade_date": str(rows[0][0]), "close": cl,
               "trend": trend, "trend_level": tlevel, "ma_arrangement": ma_arr,
               "position": {"ma5": ("上方" if ma5 and cl>ma5 else "下方"),
                            "ma10": ("上方" if ma10 and cl>ma10 else "下方"),
                            "ma20": ("上方" if ma20 and cl>ma20 else "下方"),
                            "ma60": ("上方" if ma60 and cl>ma60 else "下方")},
               "support": {"s1": s1}, "pressure": {"p1": p1},
               "recent_high_10d": max(rh) if rh else None,
               "recent_low_10d": min(rl) if rl else None,
               "break_signals": bs, "break_up_signals": bus})

# ====================== 11. 综合评分 ======================
@app.route("/api/strategy/score")
@req("ts_code")
def strategy_score():
    ts = request.args.get("ts_code","").strip()
    days = int(request.args.get("days", 120))
    rows = qr("""
        SELECT trade_date,open,close,volume,ma5,ma10,ma20,ma60,ma120,ma250,support_1,pressure_1
        FROM stock_daily_price WHERE ts_code=%s
        ORDER BY trade_date DESC LIMIT %s
    """, (ts, min(days, 250)))
    if not rows or len(rows) < 20: return er("数据不足", 404)
    cl = sf(rows[0][2]); vol = si(rows[0][3])
    ma5, ma10, ma20, ma60, ma120, ma250 = sf(rows[0][4]), sf(rows[0][5]), sf(rows[0][6]), sf(rows[0][7]), sf(rows[0][8]), sf(rows[0][9])
    s1, p1 = sf(rows[0][10]), sf(rows[0][11])
    ts_sc = 0.0
    if ma20 and cl>ma20: ts_sc += 20
    if ma60 and cl>ma60: ts_sc += 10
    if ma250 and cl>ma250: ts_sc