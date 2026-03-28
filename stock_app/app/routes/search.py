"""
搜索路由
GET /api/search?q=关键词&limit=20
"""

import os, sys
_routes_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(_routes_dir)
sys.path.insert(0, _app_dir)

from flask import Blueprint, jsonify, request
from ..utils.db import rows
import urllib.parse

bp = Blueprint("search", __name__, url_prefix="/api")


def api_ok(data=None, msg="success"):
    return jsonify({"code": 0, "msg": msg, "data": data})


@bp.route("/search")
def search():
    # 优先从 query string 拿，其次从 path 拿
    q = request.args.get("q", "").strip()
    if not q:
        return api_ok({"items": [], "keyword": "", "total": 0})

    limit = min(int(request.args.get("limit", 20)), 100)

    # 用 URL 编码避免 SQL 注入
    like = f"%{q}%"
    keyword = q

    items = rows(
        "SELECT b.ts_code, b.name, b.industry, b.market, b.symbol, "
        "  p.close, p.pct_change "
        "FROM stock_basic b "
        "LEFT JOIN stock_daily_price p ON b.ts_code=p.ts_code "
        "  AND p.trade_date=(SELECT MAX(trade_date) FROM stock_daily_price) "
        "WHERE b.name LIKE %s OR b.ts_code LIKE %s OR b.symbol LIKE %s "
        "ORDER BY b.name LIMIT %s",
        (like, like, like, limit)
    )

    return api_ok({
        "items": items,
        "keyword": keyword,
        "total": len(items),
    })
