"""
市场 & 报告路由
GET /api/market/overview
GET /api/report/daily
GET /api/health
GET /api/status
"""
import os, sys
_routes_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(_routes_dir)
sys.path.insert(0, _app_dir)

import datetime as dt
from flask import Blueprint, jsonify, request
from app.utils.db import rows, row, scalar

bp = Blueprint("market", __name__, url_prefix="/api")


def api_ok(data=None, msg="success"):
    return jsonify({"code": 0, "msg": msg, "data": data})


def api_err(msg="error", code=1):
    return jsonify({"code": code, "msg": msg})


# ── 接口8：市场概况 ────────────────────────────
@bp.route("/market/overview")
def market_overview():
    r = row("SELECT * FROM stock_market_overview ORDER BY trade_date DESC LIMIT 1")
    if not r:
        # 从 price 表实时计算
        latest = scalar("SELECT MAX(trade_date) FROM stock_daily_price")
        return api_ok({
            "trade_date": str(latest) if latest else None,
            "rise_count": scalar("SELECT COUNT(*) FROM stock_daily_price WHERE trade_date=%s AND pct_change > 0", (latest,)) or 0,
            "fall_count": scalar("SELECT COUNT(*) FROM stock_daily_price WHERE trade_date=%s AND pct_change < 0", (latest,)) or 0,
            "limit_up_count": scalar("SELECT COUNT(*) FROM stock_daily_price WHERE trade_date=%s AND pct_change >= 9.9", (latest,)) or 0,
            "limit_down_count": scalar("SELECT COUNT(*) FROM stock_daily_price WHERE trade_date=%s AND pct_change <= -9.9", (latest,)) or 0,
            "avg_pct": scalar("SELECT AVG(pct_change) FROM stock_daily_price WHERE trade_date=%s", (latest,)) or 0,
        })
    return api_ok(r)


# ── 接口12：每日复盘简报 ────────────────────────
@bp.route("/report/daily")
def report_daily():
    latest = scalar("SELECT MAX(trade_date) FROM stock_daily_price")
    if not latest:
        return api_err("无价格数据", code=404)

    trade_date = latest

    # 涨停股 TOP10（需 JOIN 获取 name）
    lu_rows = rows("""
        SELECT p.ts_code, b.name, b.industry, p.close, p.pct_change
        FROM stock_daily_price p
        JOIN stock_basic b ON p.ts_code=b.ts_code
        WHERE p.pct_change >= 9.9 AND p.trade_date=%s
        ORDER BY p.pct_change DESC LIMIT 10
    """, (trade_date,))

    # 强势板块（JOIN 获取行业）
    sec_rows = rows("""
        SELECT s.industry,
               AVG(p.pct_change) as avg_pct,
               COUNT(*) as stock_count,
               SUM(CASE WHEN p.pct_change > 0 THEN 1 ELSE 0 END) as rise_count,
               SUM(CASE WHEN p.pct_change < 0 THEN 1 ELSE 0 END) as fall_count,
               SUM(CASE WHEN p.pct_change >= 9.9 THEN 1 ELSE 0 END) as limit_up_count,
               SUM(CASE WHEN p.pct_change <= -9.9 THEN 1 ELSE 0 END) as limit_down_count
        FROM stock_daily_price p
        JOIN stock_basic s ON p.ts_code=s.ts_code
        WHERE p.trade_date=%s AND s.industry IS NOT NULL AND s.industry != ''
        GROUP BY s.industry
        HAVING COUNT(*) >= 3
        ORDER BY avg_pct DESC LIMIT 10
    """, (trade_date,))

    # 行业板块分析
    sector_analysis = []
    for s in sec_rows:
        industry = s["industry"]
        rise_count = s["rise_count"] or 0
        stock_count = s["stock_count"] or 0
        avg_pct = float(s["avg_pct"] or 0)
        rise_ratio = rise_count / stock_count * 100 if stock_count else 0

        if rise_ratio >= 70 and avg_pct >= 3:
            strength = "极强"
        elif rise_ratio >= 50 and avg_pct >= 2:
            strength = "偏强"
        elif rise_ratio >= 30 and avg_pct >= 1:
            strength = "中性"
        elif avg_pct < -1:
            strength = "偏弱"
        else:
            strength = "温和"

        # 龙头股
        top_stocks = rows("""
            SELECT p.ts_code, b.name, p.close, p.pct_change, p.rise_days
            FROM stock_daily_price p
            JOIN stock_basic b ON p.ts_code=b.ts_code
            WHERE p.trade_date=%s AND b.industry=%s
            ORDER BY p.pct_change DESC LIMIT 3
        """, (trade_date, industry))

        parts = []
        if rise_ratio >= 70: parts.append(f"板块普涨（{rise_ratio:.0f}%个股上涨）")
        if avg_pct >= 3: parts.append(f"平均涨幅{avg_pct:.1f}%，强势领涨")
        if any(x["pct_change"] and x["pct_change"] >= 9.9 for x in top_stocks): parts.append("板块有涨停股")
        if any(x["rise_days"] and x["rise_days"] >= 3 for x in top_stocks): parts.append("有个股连续3日上涨")

        sector_analysis.append({
            "industry": industry,
            "avg_pct": round(avg_pct, 2),
            "rise_count": rise_count,
            "fall_count": s["fall_count"] or 0,
            "limit_up_count": s["limit_up_count"] or 0,
            "limit_down_count": s["limit_down_count"] or 0,
            "stock_count": stock_count,
            "strength": strength,
            "analysis": "；".join(parts) if parts else f"板块涨跌幅{avg_pct:.1f}%，整体平稳",
            "top_stocks": [
                {"ts_code": x["ts_code"], "name": x["name"],
                 "close": float(x["close"]) if x["close"] else 0,
                 "pct": round(float(x["pct_change"]), 2) if x["pct_change"] else 0,
                 "rise_days": x["rise_days"] or 0}
                for x in top_stocks
            ],
            "rise_pct": round(rise_ratio, 1),
        })

    # 市场情绪
    rise = scalar("SELECT COUNT(*) FROM stock_daily_price WHERE trade_date=%s AND pct_change > 0", (trade_date,)) or 0
    fall = scalar("SELECT COUNT(*) FROM stock_daily_price WHERE trade_date=%s AND pct_change < 0", (trade_date,)) or 0
    lu = scalar("SELECT COUNT(*) FROM stock_daily_price WHERE trade_date=%s AND pct_change >= 9.9", (trade_date,)) or 0
    ld = scalar("SELECT COUNT(*) FROM stock_daily_price WHERE trade_date=%s AND pct_change <= -9.9", (trade_date,)) or 0
    avg_pct_all = float(scalar("SELECT AVG(pct_change) FROM stock_daily_price WHERE trade_date=%s", (trade_date,)) or 0)
    emotion_score = min(100, max(0, int(50 + avg_pct_all * 15 + lu * 0.5)))

    if emotion_score >= 70: emotion_label = "极强赚钱效应 ✦"
    elif emotion_score >= 50: emotion_label = "偏强赚钱效应"
    elif emotion_score >= 30: emotion_label = "情绪一般"
    else: emotion_label = "亏钱效应明显"

    concerns = []
    if ld > lu * 2: concerns.append("跌停股数量偏多，注意市场情绪风险")
    if avg_pct_all < -1: concerns.append("市场整体跌幅较大，谨慎操作")
    if lu == 0: concerns.append("市场无涨停，情绪低迷")
    if not concerns: concerns.append("市场无明显异常，关注强势板块机会")

    return api_ok({
        "trade_date": str(trade_date),
        "market": {
            "rise_count": rise,
            "fall_count": fall,
            "limit_up_count": lu,
            "limit_down_count": ld,
            "avg_pct": round(avg_pct_all, 2),
            "emotion_score": emotion_score,
            "market_emotion": emotion_label,
        },
        "hot_sectors": [s["industry"] for s in sector_analysis[:5]],
        "sector_analysis": sector_analysis,
        "concerns": concerns,
        "limit_up_stocks": [
            {"ts_code": x["ts_code"], "name": x["name"], "close": float(x["close"]) if x["close"] else 0,
             "pct": round(float(x["pct_change"]), 2) if x["pct_change"] else 0,
             "industry": x.get("industry", "")}
            for x in lu_rows
        ],
    })


# ── 健康检查 & 状态 ──────────────────────────────────
@bp.route("/health")
def health_check():
    return api_ok({"status": "ok", "time": dt.datetime.now().isoformat()})


@bp.route("/status")
def api_status():
    stock_count = scalar("SELECT COUNT(*) FROM stock_basic") or 0
    price_count = scalar("SELECT COUNT(*) FROM stock_daily_price") or 0
    latest_date = row("SELECT MAX(trade_date) as d FROM stock_daily_price")
    return api_ok({
        "stock_count": stock_count,
        "price_count": price_count,
        "latest_trade_date": str(latest_date["d"]) if latest_date else None,
        "server_time": dt.datetime.now().isoformat(),
    })
