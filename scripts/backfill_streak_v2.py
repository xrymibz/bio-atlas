#!/usr/bin/env python3
"""纯SQL回刷 rise_days/fall_days（MySQL 8.0窗口函数版）
用 LAG() 取昨日收盘，在同一个查询里计算 streak"""

import sys
import mysql.connector
from mysql.connector import pooling

DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "OpenClaw@2026",
    "database": "a_stock_data",
    "charset": "utf8mb4",
    "autocommit": True
}

cnx_pool = pooling.MySQLConnectionPool(pool_name="streak3", pool_size=4, pool_reset_session=True, **DB_CONFIG)

def run():
    conn = cnx_pool.get_connection()
    cur = conn.cursor()

    # 确保字段存在
    for col in ["rise_days", "fall_days"]:
        try:
            cur.execute(f"ALTER TABLE stock_daily_price ADD COLUMN {col} INT DEFAULT 0")
            conn.commit()
            print(f"新增 {col}")
        except Exception as e:
            if "Duplicate" in str(e) or "already exists" in str(e):
                print(f"{col} 已存在，跳过")
            else:
                print(f"{e}")

    # 先用0初始化（安全重刷）
    print("初始化字段为0...")
    cur.execute("UPDATE stock_daily_price SET rise_days=0, fall_days=0")
    conn.commit()
    print(f"已初始化 {cur.rowcount} 条")

    # 构造统计SQL：对于每只股票，按日期升序排列后，
    # 用 LAG(close) 获取昨日收盘，比较得到 direction，
    # 再用条件累计和计算连涨/连跌
    update_sql = """
    UPDATE stock_daily_price p
    JOIN (
        SELECT id, ts_code, trade_date,
               direction,
               SUM(is_up)   OVER (PARTITION BY ts_code, up_group ORDER BY trade_date) AS rise_days,
               SUM(is_down) OVER (PARTITION BY ts_code, down_group ORDER BY trade_date) AS fall_days
        FROM (
            SELECT id, ts_code, trade_date, close,
                   LAG(close) OVER w AS prev_close,
                   CASE WHEN close > LAG(close) OVER w THEN 1 WHEN close < LAG(close) OVER w THEN -1 ELSE 0 END AS direction,
                   (CASE WHEN close > LAG(close) OVER w THEN 1 ELSE 0 END) AS is_up,
                   (CASE WHEN close < LAG(close) OVER w THEN 1 ELSE 0 END) AS is_down,
                   COUNT(CASE WHEN close = LAG(close) OVER w THEN 1 END) OVER w AS eq_count
            FROM stock_daily_price
            WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date)
        ) AS with_lag
        WHERE direction != 0
        GROUP BY id, ts_code, trade_date, direction,
                 eq_count,
                 SUM(CASE WHEN direction = 1  THEN 1 ELSE 0 END) OVER (PARTITION BY ts_code ORDER BY trade_date),
                 SUM(CASE WHEN direction = -1 THEN 1 ELSE 0 END) OVER (PARTITION BY ts_code ORDER BY trade_date)
    ) AS calc
    ON p.id = calc.id
    SET p.rise_days = calc.rise_days, p.fall_days = calc.fall_days
    """

    print("回刷 streak（分批）...")
    batch = 0
    total = 0
    while True:
        cur.execute(f"""
            UPDATE stock_daily_price p
            JOIN (
                SELECT id, ts_code, trade_date,
                       direction,
                       SUM(is_up)   OVER (PARTITION BY ts_code, up_group ORDER BY trade_date) AS rise_days,
                       SUM(is_down) OVER (PARTITION BY ts_code, down_group ORDER BY trade_date) AS fall_days
                FROM (
                    SELECT id, ts_code, trade_date, close,
                           LAG(close) OVER (PARTITION BY ts_code ORDER BY trade_date) AS prev_close,
                           CASE WHEN close > LAG(close) OVER (PARTITION BY ts_code ORDER BY trade_date) THEN 1
                                WHEN close < LAG(close) OVER (PARTITION BY ts_code ORDER BY trade_date) THEN -1
                                ELSE 0 END AS direction,
                           (CASE WHEN close > LAG(close) OVER (PARTITION BY ts_code ORDER BY trade_date) THEN 1 ELSE 0 END) AS is_up,
                           (CASE WHEN close < LAG(close) OVER (PARTITION BY ts_code ORDER BY trade_date) THEN 1 ELSE 0 END) AS is_down,
                           SUM(CASE WHEN close = LAG(close) OVER (PARTITION BY ts_code ORDER BY trade_date) THEN 1 ELSE 0 END)
                             OVER (PARTITION BY ts_code ORDER BY trade_date) AS eq_count
                    FROM stock_daily_price
                ) AS with_lag
                WHERE direction != 0
            ) AS calc
            ON p.id = calc.id
            SET p.rise_days = calc.rise_days, p.fall_days = calc.fall_days
            LIMIT 20000
        """)
        conn.commit()
        n = cur.rowcount
        batch += 1
        total += n
        print(f"  批次{batch}: 更新 {n} 条 (累计{total})")
        if n < 20000:
            print(f"完成，共 {total} 条")
            break

    cur.close()
    conn.close()

if __name__ == "__main__":
    run()
