#!/usr/bin/env python3
"""
回填 rise_5d、avg_vol_20、high_20d 三个预计算字段
原理：按 ts_code + trade_date 正序遍历，用滚动窗口计算
"""
import pymysql
from collections import defaultdict

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "OpenClaw@2026",
    "database": "a_stock_data",
    "charset": "utf8mb4"
}

BATCH = 500

def backfill():
    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("读取全部历史数据...")
    cur.execute("""
        SELECT id, ts_code, trade_date, close, volume, pct_change
        FROM stock_daily_price
        ORDER BY ts_code ASC, trade_date ASC
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"共 {total} 条记录")

    # 按 ts_code 分组
    groups = defaultdict(list)
    for rid, ts, td, close, vol, pct in rows:
        groups[ts].append((rid, td, close, vol, pct))

    print("计算预计算字段...")
    updates = []
    for ts, recs in groups.items():
        closes = []
        vols = []
        pcts = []
        for rid, td, close, vol, pct in recs:
            closes.append(close or 0)
            vols.append(vol or 0)
            pcts.append(pct or 0)
            n = len(closes)

            rise_5d = round(sum(pcts[-5:]), 4)
            avg_vol_20 = round(sum(vols[-20:]) / min(20, n), 2)
            high_20d = round(max(closes[-20:]) if closes[-20:] else (close or 0), 2)

            updates.append((rise_5d, avg_vol_20, high_20d, rid))

    cur.close()
    print(f"开始回填 {len(updates)} 条...")

    cur2 = conn.cursor()
    for i in range(0, len(updates), BATCH):
        batch = updates[i:i+BATCH]
        sql = "UPDATE stock_daily_price SET rise_5d=%s, avg_vol_20=%s, high_20d=%s WHERE id=%s"
        cur2.executemany(sql, batch)
        conn.commit()
        print(f"  已更新 {min(i+BATCH, len(updates))}/{len(updates)}")
    cur2.close()
    conn.close()
    print("✅ 回填完成！")

if __name__ == "__main__":
    backfill()
