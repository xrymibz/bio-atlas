"""
数据库工具模块 - 连接池 + 基础查询封装
"""
import logging
from mysql.connector import pooling
from flask import current_app

logger = logging.getLogger(__name__)

# 全局连接池（初始化前为 None）
_pool = None


def init_pool(db_config):
    """从 config 初始化连接池（应用启动时调用一次）"""
    global _pool
    _pool = pooling.MySQLConnectionPool(
        pool_name="stock_pool",
        pool_size=db_config.get("DB_POOL_SIZE", 16),
        pool_reset_session=True,
        host=db_config["DB_HOST"],
        user=db_config["DB_USER"],
        password=db_config["DB_PASSWORD"],
        database=db_config["DB_NAME"],
        charset=db_config.get("DB_CHARSET", "utf8mb4"),
        autocommit=True,
    )
    logger.info("数据库连接池初始化完成，pool_size=%s", db_config.get("DB_POOL_SIZE", 16))


def get_pool():
    if _pool is None:
        raise RuntimeError("数据库连接池未初始化，请先调用 init_pool()")
    return _pool


def get_db():
    """从连接池获取一个连接（用完必须 close()）"""
    return get_pool().get_connection()


def rows(sql, args=None):
    """查询多行，返回 list[dict] 或 list[tuple]"""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, args or ())
        result = cur.fetchall()
        cur.close()
        return result
    finally:
        conn.close()


def row(sql, args=None):
    """查询单行，返回 dict 或 tuple"""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, args or ())
        result = cur.fetchone()
        cur.close()
        return result
    finally:
        conn.close()


def scalar(sql, args=None):
    """查询单个值（标量查询）"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(sql, args or ())
        result = cur.fetchone()
        cur.close()
        return result[0] if result else None
    finally:
        conn.close()
