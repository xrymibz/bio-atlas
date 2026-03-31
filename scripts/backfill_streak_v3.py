#!/usr/bin/env python3
"""回刷 rise_days/fall_days
逐只股票处理（避免内存爆掉），用 MySQL 的 UPDATE FROM SELECT"""

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

cnx_pool = pooling.MySQLConnectionPool(pool_name="streak4", pool_size=4, pool_reset_session=True, **DB_CONFIG)

def sf(v):
    try: return float(v) if v is not None and str(v).strip() not in ("", "nan", "None") else None
    except: return None

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
                print(f"{col} 已存在")
            else:
                print(f"{e}")

    # 获取所有股票代码
    cur.execute("SELECT DISTINCT ts_code FROM stock_daily_price ORDER BY ts_code")
    codes = [r[0] for r in cur.fetchall()]
    print(f"共 {len(codes)} 只股票")
    conn.close()

    total = 0
    t0 = time.time()
    for i, ts_code in enumerate(codes):
        conn = cnx_pool.get_connection()
        cur = conn.cursor()

        # 逐只股票按日期升序取出
        cur.execute("""
            SELECT id, trade_date, close FROM stock_daily_price
            WHERE ts_code = %s ORDER BY trade_date ASC
        """, (ts_code,))
        rows = cur.fetchall()  # [(id, trade_date, close), ...]

        if len(rows) < 2:
            cur.close()
            conn.close()
            continue

        # 预计算：对于每个id，计算对应的rise_days和fall_days
        updates = []
        prev_close = sf(rows[0][2])
        cur_rise = cur_fall = 0

        # 第一条：与前一天（表里没有则从自己开始）
        updates.append((0, 0, rows[0][0]))

        for j in range(1, len(rows)):
            curr_close = sf(rows[j][2])
            if curr_close is None or prev_close is None:
                updates.append((0, 0, rows[j][0]))
                prev_close = curr_close
                cur_rise = cur_fall = 0
                continue

            if curr_close > prev_close:
                cur_rise += 1
                cur_fall = 0
            elif curr_close < prev_close:
                cur_fall += 1
                cur_rise = 0
            else:
                cur_rise = cur_fall = 0

            updates.append((cur_rise, cur_fall, rows[j][0]))
            prev_close = curr_close

        # 批量更新这只股票
        cur.executemany("""
            UPDATE stock_daily_price SET rise_days=%s, fall_days=%s WHERE id=%s
        """, updates)
        conn.commit()
        total += len(updates)

        cur.close()
        conn.close()

        if (i + 1) % 200 == 0:
            elapsed = time.time() - t0
            print(f"  已处理 {i+1}/{len(codes)} 只 ({total}条, {elapsed:.0f}s)")

    print(f"完成！共更新 {total} 条，耗时 {time.time()-t0:.0f}秒")

if __name__ == "__main__":
    run()
