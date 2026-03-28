"""
路由蓝图汇总
"""
from .stock import bp as stock_bp
from .strategy import bp as strategy_bp
from .market import bp as market_bp
from .search import bp as search_bp

__all__ = ["stock_bp", "strategy_bp", "market_bp", "search_bp"]
