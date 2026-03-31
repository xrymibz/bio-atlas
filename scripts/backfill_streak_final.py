#!/usr/bin/env python3
"""安全回刷 rise_days/fall_days — 逐只股票处理，内存安全"""
import sys, time

def sf(v):
    try: return float(v) if v is not None and str(v).strip() not in ("","nan","None") else None
    except: return None

def main():
    import mysql.connector
    conn = mysql.connector.connect(
        host="127.0.0.1", user="root",
        password="OpenClaw@2026", database="a_stock_data",
        charset="utf8mb4", autocommit=False
    )
    cur = conn.cursor()

    # 确保字段存在
    for col in ["rise_days", "fall_days"]:
        try:
            cur.execute(f"ALTER TABLE stock_daily_price ADD COLUMN {col} SMALLINT UNSIGNED DEFAULT 0")
            conn.commit()
        except:
            pass

    # 获取所有股票代码
    cur.execute("SELECT DISTINCT ts_code FROM stock_daily_price ORDER BY ts_code")
    codes = [r[0] for r in cur.fetchall()]
    total_stocks = len(codes)
    print(f"共 {total_stocks} 只股票", file=sys.stderr)

    t0 = time.time()
    done = 0

    for idx, ts_code in enumerate(codes):
        # 逐只股票按日期升序取出
        cur.execute("""
            SELECT id, close FROM stock_daily_price
            WHERE ts_code = %s ORDER BY trade_date ASC
        """, (ts_code,))
        rows = cur.fetchall()

        if len(rows) < 2:
            cur.fetchall()  # 清空结果集
            continue

        updates = []
        prev_c = None
        cur_rise = cur_fall = 0

        for row_id, close in rows:
            c = sf(close)
            if c is None or prev_c is None:
                updates.append((0, 0, row_id))
                prev_c = c
                cur_rise = cur_fall = 0
                continue

            if c > prev_c:
                cur_rise += 1; cur_fall = 0
            elif c < prev_c:
                cur_fall += 1; cur_rise = 0
            else:
                cur_rise = cur_fall = 0

            updates.append((cur_rise, cur_fall, row_id))
            prev_c = c

        # 批量更新这只股票
        cur.executemany(
            "UPDATE stock_daily_price SET rise_days=%s, fall_days=%s WHERE id=%s",
            updates
        )
        conn.commit()
        done += 1

        if done % 200 == 0:
            elapsed = time.time() - t0
            print(f"  {done}/{total_stocks} ({elapsed:.0f}s)", file=sys.stderr)

    elapsed = time.time() - t0
    print(f"完成！{done} 只股票，耗时 {elapsed:.0f}s", file=sys.stderr)
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
