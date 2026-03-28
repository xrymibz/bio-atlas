"""
策略路由 - 强势股池、趋势、评分、金叉、MACD、追踪
"""
import os, sys
_routes_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(_routes_dir)
sys.path.insert(0, _app_dir)

import datetime as dt
from flask import Blueprint, jsonify, request
from app.utils.db import rows, row, scalar, get_db
from app.utils.helpers import calc_rsi, calc_ma, calc_macd

bp = Blueprint("strategy", __name__, url_prefix="/api/strategy")


def api_ok(data=None, msg="success"):
    return jsonify({"code": 0, "msg": msg, "data": data})


def api_err(msg="error", code=1):
    return jsonify({"code": code, "msg": msg})


def _latest_date():
    return scalar("SELECT MAX(trade_date) FROM stock_daily_price")


def _latest_ma_date():
    """最近一个有 MA 数据的交易日"""
    d = scalar(
        "SELECT MAX(trade_date) FROM stock_daily_price "
        "WHERE ma5 IS NOT NULL AND ma20 IS NOT NULL AND close IS NOT NULL"
    )
    return d or _latest_date()


# ── 接口9：强势股池（修正列名）───────────────
@bp.route("/pool")
def strategy_pool():
    sort_type = request.args.get("type", "score")
    top = min(int(request.args.get("top", 20)), 100)
    latest = _latest_ma_date()

    # 直接从 price + basic 表联合查询（price表有ma5/ma20/rise_days/fall_days/rise_5d）
    items = rows(f"""
        SELECT p.ts_code, b.name, b.industry,
               p.close, p.pct_change,
               p.ma5, p.ma10, p.ma20, p.ma60,
               COALESCE(p.volume_ratio, 1.0) as volume_ratio,
               p.rise_5d, p.high_20d,
               p.rise_days, p.fall_days
        FROM stock_daily_price p
        JOIN stock_basic b ON p.ts_code = b.ts_code
        WHERE p.trade_date = %s
          AND p.close IS NOT NULL AND p.ma5 IS NOT NULL AND p.ma20 IS NOT NULL
        ORDER BY p.pct_change DESC
        LIMIT %s
    """, (latest, top))

    # 按类型重新排序
    if sort_type == "drawdown":
        # 从预计算表读回撤（如果 indicator 表有 dif/dea/macd 才能算，这里用 fall_days 代替）
        items = sorted(items, key=lambda x: x.get("fall_days") or 0, reverse=True)[:top]
    elif sort_type == "rise_5d_pct":
        items = sorted(items, key=lambda x: float(x.get("rise_5d") or 0), reverse=True)[:top]
    elif sort_type == "rise_streak":
        items = sorted([i for i in items if (i.get("rise_days") or 0) > 0],
                       key=lambda x: x["rise_days"], reverse=True)[:top]

    return api_ok({
        "items": items,
        "total": len(items),
        "strategy": "站上MA20 + 近5日涨幅 + 放量（volume_ratio未启用）",
        "trade_date": str(latest),
    })


# ── 接口10：趋势与破位 ───────────────────────
@bp.route("/trend")
def strategy_trend():
    ts_code = request.args.get("ts_code")
    if not ts_code:
        return api_err("缺少 ts_code", code=400)

    price_rows = rows(
        "SELECT trade_date, close, high, low FROM stock_daily_price "
        "WHERE ts_code=%s ORDER BY trade_date DESC LIMIT 120",
        (ts_code,)
    )
    if not price_rows:
        return api_err("无价格数据", code=404)

    closes = [float(r["close"]) for r in price_rows][::-1]
    highs = [float(r["high"]) for r in price_rows][::-1]
    lows = [float(r["low"]) for r in price_rows][::-1]
    latest = price_rows[0]
    close = closes[-1]

    # 从 price 表直接读 MA（已有 ma5/ma10/ma20/ma60）
    latest_row = row(
        "SELECT ma5, ma10, ma20, ma60 FROM stock_daily_price "
        "WHERE ts_code=%s ORDER BY trade_date DESC LIMIT 1",
        (ts_code,)
    )
    ma5 = latest_row["ma5"]
    ma10 = latest_row["ma10"]
    ma20 = latest_row["ma20"]
    ma60 = latest_row["ma60"]

    # 趋势判断
    if ma5 and ma20:
        if ma5 > ma20 * 1.02:
            trend, tlevel = "上升", "强势" if ma5 > ma20 * 1.05 else "偏强"
        elif ma5 < ma20 * 0.98:
            trend, tlevel = "下降", "弱势" if ma5 < ma20 * 0.95 else "偏弱"
        else:
            trend, tlevel = "震荡", "中性"
    else:
        trend, tlevel = "震荡", "中性"

    # MA 排列
    ma_vals = [(n, v) for n, v in [("MA5", ma5), ("MA10", ma10), ("MA20", ma20), ("MA60", ma60)] if v]
    ma_vals.sort(key=lambda x: x[1], reverse=True)
    arr_str = " > ".join([f"{n}{v:.2f}" for n, v in ma_vals]) if ma_vals else "-"

    # 破位
    break_down, break_up = [], []
    if ma20 and close < ma20 * 0.97:
        break_down.append(f"跌破MA20({ma20:.2f})")
    if ma60 and close < ma60 * 0.97:
        break_down.append(f"跌破MA60({ma60:.2f})")
    if ma20 and close > ma20 * 1.03:
        break_up.append(f"突破MA20({ma20:.2f})")
    if ma60 and close > ma60 * 1.03:
        break_up.append(f"突破MA60({ma60:.2f})")

    # 支撑压力
    low10 = min(lows[:10]) if lows[:10] else None
    high10 = max(highs[:10]) if highs[:10] else None

    return api_ok({
        "trend": trend, "trend_level": tlevel,
        "ma_arrangement": arr_str,
        "break_signals": break_down,
        "break_up_signals": break_up,
        "recent_low_10d": round(low10, 2) if low10 else None,
        "recent_high_10d": round(high10, 2) if high10 else None,
        "support": {"s1": round(low10 * 0.99, 2) if low10 else None},
        "pressure": {"p1": round(high10 * 1.01, 2) if high10 else None},
    })


# ── 接口11：综合评分 ─────────────────────────
@bp.route("/score")
def strategy_score():
    ts_code = request.args.get("ts_code")
    if not ts_code:
        return api_err("缺少 ts_code", code=400)

    latest = row(
        "SELECT p.ts_code, b.name, b.industry, p.close, p.pct_change, "
        "  p.ma5, p.ma10, p.ma20, p.volume_ratio, p.rise_5d "
        "FROM stock_daily_price p "
        "JOIN stock_basic b ON p.ts_code=b.ts_code "
        "WHERE p.ts_code=%s ORDER BY p.trade_date DESC LIMIT 1",
        (ts_code,)
    )
    if not latest:
        return api_err("股票不存在", code=404)

    close = float(latest["close"] or 0)
    pct = float(latest["pct_change"] or 0)
    ma5 = latest["ma5"]
    ma20 = latest["ma20"]
    vr = float(latest["volume_ratio"] or 1.0)
    rise5 = float(latest["rise_5d"] or 0)

    # 粗略评分（基于已有字段）
    score = 50 + int(pct * 3) + int(rise5 * 2)
    score = max(0, min(100, score))
    level = "优秀" if score >= 80 else "良好" if score >= 65 else "一般" if score >= 50 else "较差"

    return api_ok({
        "total_score": score,
        "level": level,
        "dimensions": {
            "trend": {"score": max(0, min(40, 20 + int((float(ma5) / float(ma20) - 1) * 100) if ma5 and ma20 else 20)), "max": 40},
            "momentum": {"score": max(0, min(25, 12 + int(pct * 5))), "max": 25},
            "volume": {"score": max(0, min(15, int(vr * 5))), "max": 15},
            "valuation": {"score": max(0, min(20, 10 + int(rise5))), "max": 20},
        },
    })


# ── 接口14：MA金叉（基于price表实时计算）────────────
@bp.route("/golden_cross")
def golden_cross():
    page = max(1, int(request.args.get("page", 1)))
    page_size = min(50, int(request.args.get("page_size", 50)))
    offset = (page - 1) * page_size

    # 从 price 表找：ma5 上穿 ma20（金叉）
    # 需要历史数据来判断
    items = rows(f"""
        SELECT p.ts_code, b.name, b.industry, p.close, p.pct_change,
               p.ma5, p.ma20, p.volume_ratio, p.rise_5d, p.rise_days
        FROM stock_daily_price p
        JOIN stock_basic b ON p.ts_code=b.ts_code
        WHERE p.trade_date=(SELECT MAX(trade_date) FROM stock_daily_price p2 WHERE p2.ma5 IS NOT NULL AND p2.ma20 IS NOT NULL)
          AND p.ma5 IS NOT NULL AND p.ma20 IS NOT NULL
          AND p.ma5 > p.ma20 AND p.ma5 < p.ma20 * 1.05
          AND p.close IS NOT NULL
        ORDER BY p.rise_days DESC, p.pct_change DESC
        LIMIT %s OFFSET %s
    """, (page_size, offset))

    _ma_date = _latest_ma_date()
    total = scalar(
        "SELECT COUNT(*) FROM stock_daily_price p "
        "WHERE p.trade_date=%s AND p.ma5 > p.ma20 AND p.ma5 < p.ma20 * 1.05"
    , (_ma_date,)) or 0

    return api_ok({
        "items": items,
        "total": total,
        "page": page,
        "pages": (total + page_size - 1) // page_size,
        "trade_date": str(_latest_ma_date()),
    })


# ── 接口16：MACD 信号 ───────────────────────
@bp.route("/macd_cross")
def macd_cross():
    # 从 indicator 表读 dif/dea/macd（MACD 三值）
    items = rows("""
        SELECT p.ts_code, b.name, b.industry, p.close, p.pct_change,
               i.dif, i.dea, i.macd, i.volume_ratio
        FROM stock_daily_indicator i
        JOIN stock_daily_price p ON i.ts_code=p.ts_code AND i.trade_date=p.trade_date
        JOIN stock_basic b ON p.ts_code=b.ts_code
        WHERE p.trade_date=(SELECT MAX(trade_date) FROM stock_daily_price)
          AND i.dif IS NOT NULL AND i.dea IS NOT NULL AND i.macd IS NOT NULL
          AND i.dif > 0 AND i.macd > 0
        ORDER BY i.macd DESC
        LIMIT 100
    """)
    return api_ok({
        "items": items,
        "total": len(items),
        "trade_date": str(_latest_date()),
    })


# ── 金叉追踪写入 ──────────────────────────────
@bp.route("/golden_cross/track_update", methods=["POST"])
def track_update():
    data = request.get_json(silent=True) or {}
    ts_codes = data.get("ts_codes", [])
    if not ts_codes:
        return api_err("ts_codes 不能为空", code=400)

    today = dt.date.today().isoformat()
    conn = get_db()
    cur = conn.cursor()
    added = 0
    for code in ts_codes:
        exists = row(
            "SELECT id FROM golden_cross_track WHERE ts_code=%s AND status=0",
            (code,)
        )
        if not exists:
            # 查基本信息
            info = row("SELECT name, industry, close, ma5, ma20 FROM stock_daily_price p JOIN stock_basic b ON p.ts_code=b.ts_code WHERE p.ts_code=%s ORDER BY p.trade_date DESC LIMIT 1", (code,))
            name = info["name"] if info else code
            industry = info["industry"] if info else ""
            close = info["close"] if info else 0
            ma5 = info["ma5"] if info else 0
            ma20 = info["ma20"] if info else 0
            cur.execute(
                "INSERT INTO golden_cross_track (ts_code,name,industry,trade_date,close,ma5,ma20,status) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,0)",
                (code, name, industry, today, close, ma5, ma20)
            )
            added += 1
    conn.commit()
    cur.close()
    conn.close()
    return api_ok({"added": added, "total": len(ts_codes)})


# ── 追踪记录读取 ──────────────────────────────
@bp.route("/golden_cross/track")
def track_list():
    status = request.args.get("status", "")
    page = max(1, int(request.args.get("page", 1)))
    page_size = min(50, int(request.args.get("page_size", 30)))
    offset = (page - 1) * page_size

    where = "WHERE 1=1"
    if status == "0":
        where += " AND t.status=0"
    elif status == "1":
        where += " AND t.status=1"

    _ma_date = _latest_ma_date()
    # 用子查询避免 collation 冲突（CONVERT解决utf8mb4_unicode_ci vs utf8mb4_0900_ai_ci）
    items = rows(f"""
        SELECT t.id, t.ts_code, t.name, t.industry, t.trade_date, t.close,
               t.ma5, t.ma20, t.pct_1d, t.pct_2d, t.pct_3d, t.status,
               (SELECT pct_change FROM stock_daily_price WHERE CONVERT(ts_code USING utf8mb4)=t.ts_code AND trade_date=%s LIMIT 1) as cur_pct,
               (SELECT close FROM stock_daily_price WHERE CONVERT(ts_code USING utf8mb4)=t.ts_code AND trade_date=%s LIMIT 1) as cur_close
        FROM golden_cross_track t
        {where}
        ORDER BY t.id DESC
        LIMIT %s OFFSET %s
    """, (_ma_date, _ma_date, page_size, offset))

    total = scalar(f"SELECT COUNT(*) FROM golden_cross_track t {where}") or 0

    return api_ok({
        "items": items,
        "total": total,
        "page": page,
        "pages": (total + page_size - 1) // page_size,
    })
