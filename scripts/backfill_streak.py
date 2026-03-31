#!/usr/bin/env python3
"""回刷 stock_daily_price 表的 rise_days 和 fall_days 字段
从每只股票最早的数据开始，逐日计算当前连涨/连跌天数"""

import sys, time
sys.path.insert(0, '/root/.openclaw/workspace')

from collections import defaultdict
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

cnx_pool = pooling.MySQLConnectionPool(pool_name="streak", pool_size=8, pool_reset_session=True, **DB_CONFIG)

def get_conn():
    return cnx_pool.get_connection()

def sf(v):
    try: return float(v) if v is not None and str(v).strip() not in ("", "nan", "None") else None
    except: return None

def si(v):
    try: return int(float(v)) if v is not None and str(v).strip() not in ("", "nan", "None") else None
    except: return None

def backfill_streak():
    conn = get_conn()
    cur = conn.cursor()

    # 确保字段存在
    try:
        cur.execute("""
            ALTER TABLE stock_daily_price
            ADD COLUMN rise_days INT DEFAULT 0,
            ADD COLUMN fall_days INT DEFAULT 0
        """)
        conn.commit()
        print("新增字段 rise_days, fall_days")
    except Exception as e:
        if "Duplicate column" in str(e) or "already exists" in str(e):
            print("字段已存在，跳过")
        else:
            print(f"字段异常: {e}")

    # 获取所有股票及其全部历史（按日期升序）
    print("读取所有股票历史数据...")
    cur.execute("""
        SELECT ts_code, trade_date, close
        FROM stock_daily_price
        ORDER BY ts_code, trade_date ASC
    """)
    all_rows = cur.fetchall()
    print(f"共 {len(all_rows)} 条记录")

    # 按股票分组
    by_stock = defaultdict(list)
    for r in all_rows:
        by_stock[r[0]].append((r[1], sf(r[2])))

    print(f"共 {len(by_stock)} 只股票，开始计算...")

    updates = []
    total = 0
    for ts_code, rows in by_stock.items():
        if len(rows) < 2:
            continue
        rise = fall = 0
        for trade_date, close in rows:
            if close is None:
                updates.append((0, 0, ts_code, trade_date))
                continue
            prev_close = close_prev = None
            # 找上一日收盘价（在同一列表中）
            idx = rows.index((trade_date, close))
            if idx > 0:
                prev_close = rows[idx - 1][1]
            
            if prev_close is None:
                rise = fall = 0
            elif close > prev_close:
                rise += 1; fall = 0
            elif close < prev_close:
                fall += 1; rise = 0
            else:
                rise = fall = 0
            
            updates.append((rise, fall, ts_code, trade_date))
            total += 1

    print(f"计算完成，共 {total} 条，准备写入...")

    # 批量更新
    cur.execute("SET SQL_LOG_BIN = 0")
    conn.commit()

    chunk = 5000
    for i in range(0, len(updates), chunk):
        chunk_data = updates[i:i+chunk]
        cur.executemany("""
            UPDATE stock_daily_price
            SET rise_days = %s, fall_days = %s
            WHERE ts_code = %s AND trade_date = %s
        """, chunk_data)
        conn.commit()
        print(f"  已写入 {min(i+chunk, len(updates))}/{len(updates)} 条")

    cur.close()
    conn.close()
    print("回刷完成!")

if __name__ == "__main__":
    backfill_streak()
