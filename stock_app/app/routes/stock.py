"""
股票基础信息 & 行情数据路由
GET /api/stock/info?ts_code=000001.SZ
GET /api/stock/daily?ts_code=000001.SZ&period=5
GET /api/stock/indicator?ts_code=000001.SZ
GET /api/stock/capital?ts_code=000001.SZ
GET /api/stock/chip?ts_code=000001.SZ
GET /api/stock/events?ts_code=000001.SZ
GET /api/stock/funda?ts_code=000001.SZ
"""

import os, sys
_routes_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(_routes_dir)
sys.path.insert(0, _app_dir)

from flask import Blueprint, jsonify, request
try:
    from app.utils.db import rows, row, scalar
    from app.utils.helpers import calc_rsi, calc_ma, calc_macd, pct_str, pct_cls
except ImportError:
    from app.utils.db import rows, row, scalar
    from app.utils.helpers import calc_rsi, calc_ma, calc_macd, pct_str, pct_cls

bp = Blueprint("stock", __name__, url_prefix="/api/stock")


def api_ok(data=None, msg="success"):
    return jsonify({"code": 0, "msg": msg, "data": data})


def api_err(msg="error", code=1):
    return jsonify({"code": code, "msg": msg})


def param_required(*names):
    def deco(f):
        def fn(*args, **kwargs):
            missing = [n for n in names if not request.args.get(n)]
            if missing:
                return api_err(f"缺少参数: {', '.join(missing)}", code=400)
            return f(*args, **kwargs)
        fn.__name__ = f.__name__
        return fn
    return deco


def sf(v):
    try:
        f = float(v) if v is not None and str(v).strip() not in ("", "nan", "None") else None
        return round(f, 4) if f is not None else None
    except:
        return None


@bp.route("/info")
@param_required("ts_code")
def stock_info():
    ts_code = request.args.get("ts_code")
    r = row(
        "SELECT ts_code, name, industry, market, list_date, is_active FROM stock_basic WHERE ts_code=%s",
        (ts_code,)
    )
    if not r:
        return api_err("股票不存在", code=404)

    # 最新行情
    latest = row(
        "SELECT close, pct_change, volume, amount, high, low FROM stock_daily_price "
        "WHERE ts_code=%s ORDER BY trade_date DESC LIMIT 1",
        (ts_code,)
    )
    info = dict(r)
    if latest:
        info.update({k: latest[k] for k in ["close", "pct_change", "volume", "amount", "high", "low"]})
        info["latest_date"] = latest.get("trade_date")
        info["latest_price"] = latest.get("close")
    return api_ok(info)


@bp.route("/daily")
def stock_daily():
    ts_code = request.args.get("ts_code")
    period = int(request.args.get("period", 30))
    if not ts_code:
        return api_err("缺少 ts_code", code=400)

    items = rows(
        "SELECT trade_date, open, high, low, close, volume, amount, pct_change "
        "FROM stock_daily_price WHERE ts_code=%s ORDER BY trade_date DESC LIMIT %s",
        (ts_code, period)
    )
    return api_ok({"items": items, "total": len(items)})


@bp.route("/indicator")
def stock_indicator():
    ts_code = request.args.get("ts_code")
    if not ts_code:
        return api_err("缺少 ts_code", code=400)

    prices = rows(
        "SELECT close FROM stock_daily_price WHERE ts_code=%s ORDER BY trade_date DESC LIMIT 120",
        (ts_code,)
    )
    closes = [r["close"] for r in prices][::-1]
    if len(closes) < 5:
        return api_ok({"ma5": None, "ma10": None, "ma20": None, "ma60": None,
                       "rsi": None, "dif": None, "dea": None, "macd_hist": None})

    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)
    rsi = calc_rsi(closes)
    macd = calc_macd(closes)
    dif, dea, macd_hist = macd if macd else (None, None, None)

    return api_ok({
        "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
        "rsi": rsi, "dif": dif, "dea": dea, "macd_hist": macd_hist,
    })


@bp.route("/capital")
def stock_capital():
    ts_code = request.args.get("ts_code")
    if not ts_code:
        return api_err("缺少 ts_code", code=400)
    items = rows(
        "SELECT trade_date, close, amount, net_amount FROM stock_daily_capital "
        "WHERE ts_code=%s ORDER BY trade_date DESC LIMIT 30",
        (ts_code,)
    )
    return api_ok({"items": items, "total": len(items)})


@bp.route("/chip")
def stock_chip():
    ts_code = request.args.get("ts_code")
    if not ts_code:
        return api_err("缺少 ts_code", code=400)
    items = rows(
        "SELECT date, cost, share_ratio FROM stock_chip_distribution "
        "WHERE ts_code=%s ORDER BY date DESC LIMIT 20",
        (ts_code,)
    )
    return api_ok({"items": items, "total": len(items)})


@bp.route("/events")
def stock_events():
    ts_code = request.args.get("ts_code")
    if not ts_code:
        return api_err("缺少 ts_code", code=400)
    items = rows(
        "SELECT trade_date, event_type, event_desc FROM stock_daily_events "
        "WHERE ts_code=%s ORDER BY trade_date DESC LIMIT 20",
        (ts_code,)
    )
    return api_ok({"items": items, "total": len(items)})


@bp.route("/funda")
def stock_funda():
    ts_code = request.args.get("ts_code")
    if not ts_code:
        return api_err("缺少 ts_code", code=400)
    r = row(
        "SELECT * FROM stock_daily_funda WHERE ts_code=%s ORDER BY trade_date DESC LIMIT 1",
        (ts_code,)
    )
    return api_ok(r or {})
