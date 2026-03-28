"""
配置管理 - 所有敏感配置和数据库连接池
"""
import os

class Config:
    """生产环境配置"""
    DEBUG = False
    
    # 数据库
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "OpenClaw@2026")
    DB_NAME = os.getenv("DB_NAME", "a_stock_data")
    DB_CHARSET = "utf8mb4"
    DB_POOL_SIZE = 32

    # Flask
    JSON_AS_ASCII = False
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True


class TestingConfig(Config):
    """测试环境配置"""
    TESTING = True
    DB_NAME = "a_stock_data_test"


config = {
    "development": DevelopmentConfig(),
    "testing": TestingConfig(),
    "production": Config(),
    "default": DevelopmentConfig(),
}
