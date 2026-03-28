"""
Flask 应用工厂
"""
import os
from flask import Flask, send_from_directory

# 动态导入 config（避免相对导入歧义）
_app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, _app_root)
from config import config


def create_app(config_name=None):
    """应用工厂函数"""
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "production")

    cfg = config.get(config_name, config["production"])

    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = cfg.JSON_AS_ASCII
    app.config["MAX_CONTENT_LENGTH"] = cfg.MAX_CONTENT_LENGTH

    # 初始化数据库连接池
    from app.utils.db import init_pool
    init_pool({
        "DB_HOST": cfg.DB_HOST,
        "DB_USER": cfg.DB_USER,
        "DB_PASSWORD": cfg.DB_PASSWORD,
        "DB_NAME": cfg.DB_NAME,
        "DB_CHARSET": cfg.DB_CHARSET,
        "DB_POOL_SIZE": cfg.DB_POOL_SIZE,
    })

    # 注册蓝图
    from app.routes import stock_bp, strategy_bp, market_bp, search_bp
    app.register_blueprint(stock_bp)
    app.register_blueprint(strategy_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(search_bp)

    # 前端页面
    @app.route("/")
    def index():
        static_dir = os.path.join(_app_root, "static")
        frontend = os.path.join(static_dir, "stock_frontend.html")
        if os.path.exists(frontend):
            return send_from_directory(static_dir, "stock_frontend.html")
        return "stock_frontend.html not found", 404

    return app
