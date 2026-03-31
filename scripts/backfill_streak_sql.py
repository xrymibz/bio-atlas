#!/usr/bin/env python3
"""纯SQL回刷 rise_days/fall_days，不需要Python计算
思路：对于每只股票，按日期升序，逐日比较收盘价与昨日，用用户变量跟踪连涨/连跌计数"""

import sys, time
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

cnx_pool = pooling.MySQLConnectionPool(pool_name="streak2", pool_size=4, pool_reset_session=True, **DB_CONFIG)

def get_conn():
    return cnx_pool.get_connection()

def run():
    conn = get_conn()
    cur = conn.cursor()

    # 确保字段存在
    for col, dtype in [("rise_days", "INT DEFAULT 0"), ("fall_days", "INT DEFAULT 0")]:
        try:
            cur.execute(f"ALTER TABLE stock_daily_price ADD COLUMN {col} {dtype}")
            conn.commit()
            print(f"新增字段 {col}")
        except Exception as e:
            if "Duplicate" in str(e) or "already exists" in str(e):
                print(f"{col} 已存在")
            else:
                print(f"字段异常: {e}")

    # 逐只股票处理，避免大结果集撑爆内存
    cur.execute("SELECT COUNT(DISTINCT ts_code) FROM stock_daily_price")
    stock_count = cur.fetchone()[0]
    print(f"共 {stock_count} 只股票...")

    # 分批获取股票代码
    batch_size = 500
    offset = 0
    total_updated = 0

    while offset < stock_count:
        cur.execute(f"""
            SELECT DISTINCT ts_code FROM stock_daily_price
            ORDER BY ts_code LIMIT {batch_size} OFFSET {offset}
        """)
        codes = [r[0] for r in cur.fetchall()]
        if not codes:
            break

        for ts_code in codes:
            # 用SQL窗口函数或用户变量逐只股票计算streak
            # 方式：用户变量，按ts_code分组按日期升序处理
            cur.execute(f"""
                UPDATE stock_daily_price p,
                (
                    SELECT id,
                           ts_code, trade_date, close,
                           @prev_close := @curr_close AS prev_close,
                           @curr_close := close AS curr_close,
                           CASE
                             WHEN close > @prev_close THEN @rise := @rise + 1
                             WHEN close < @prev_close THEN @rise := 0
                             ELSE 0
                           END AS new_rise,
                           CASE
                             WHEN close < @prev_close THEN @fall := @fall + 1
                             WHEN close > @prev_close THEN @fall := 0
                             ELSE 0
                           END AS new_fall
                    FROM stock_daily_price,
                    (SELECT @rise:=0, @fall:=0, @prev_close:=NULL, @curr_close:=NULL) AS vars
                    WHERE ts_code = '{ts_code}'
                    ORDER BY trade_date ASC
                ) AS calc
                SET p.rise_days = calc.new_rise, p.fall_days = calc.new_fall
                WHERE p.id = calc.id
            """)
            total_updated += cur.rowcount

        conn.commit()
        print(f"  已处理 {offset + len(codes)}/{stock_count} 只股票")
        offset += batch_size

    print(f"回刷完成，共更新 {total_updated} 条记录")
    cur.close()
    conn.close()

if __name__ == "__main__":
    run()
