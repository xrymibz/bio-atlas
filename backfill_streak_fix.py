#!/usr/bin/env python3
"""
回填连涨/连跌天数：修复 prepare_records 中的计算逻辑
修复后重新计算所有历史记录的 rise_days 和 fall_days
"""
import pymysql
import datetime

DB_HOST = "localhost"
DB_USER = "root"
DB_PWD  = "OpenClaw@2026"
DB_NAME = "a_stock_data"
BATCH   = 500

def get_conn():
    return pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PWD,
                          database=DB_NAME, charset="utf8mb4")

def backfill_streak():
    conn = get_conn()
    cur = conn.cursor()

    # 按 ts_code + trade_date 正序，读取所有记录
    cur.execute("""
        SELECT id, ts_code, trade_date, pct_change
        FROM stock_daily_price
        ORDER BY ts_code ASC, trade_date ASC
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"共 {total} 条记录，开始回填连涨/连跌天数...")

    # 建立 id -> (pct_change, rise_days, fall_days) 的映射
    # 按 ts_code 分组处理
    from collections import defaultdict
    groups = defaultdict(list)
    for rid, ts, td, pct in rows:
        groups[ts].append((rid, td, pct))

    updates = []
    for ts, recs in groups.items():
        # recs 已经按 trade_date 正序
        rise_days = 0
        fall_days = 0
        for rid, td, pct in recs:
            pct = pct or 0
            if pct > 0:
                rise_days += 1
                fall_days = 0
            elif pct < 0:
                fall_days += 1
                rise_days = 0
            else:
                rise_days = 0
                fall_days = 0
            updates.append((rise_days, fall_days, rid))

    cur.close()

    # 批量更新
    cur2 = conn.cursor()
    updated = 0
    for i in range(0, len(updates), BATCH):
        batch = updates[i:i+BATCH]
        sql = "UPDATE stock_daily_price SET rise_days=%s, fall_days=%s WHERE id=%s"
        cur2.executemany(sql, batch)
        conn.commit()
        updated += len(batch)
        print(f"  已更新 {updated}/{len(updates)}")

    cur2.close()
    conn.close()
    print("✅ 回填完成！")

if __name__ == "__main__":
    backfill_streak()
