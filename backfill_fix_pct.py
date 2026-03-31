#!/usr/bin/env python3
"""修正 pct_change：正确公式 = (今收-昨收)/昨收 × 100"""
import mysql.connector

DB = {"host": "localhost", "user": "root", "password": "OpenClaw@2026", "database": "a_stock_data"}

def fix_pct():
    conn = mysql.connector.connect(**DB)
    c = conn.cursor()
    print("修正 stock_daily_price pct_change...")

    # 用 UPDATE JOIN 修正
    sql = """
        UPDATE stock_daily_price p
        JOIN stock_daily_price prev ON prev.ts_code = p.ts_code
          AND prev.trade_date = DATE_SUB(p.trade_date, INTERVAL 1 DAY)
        SET p.pct_change = ROUND((p.close - prev.close) / prev.close * 100, 4)
        WHERE prev.close IS NOT NULL AND prev.close != 0
          AND (p.pct_change IS NULL OR p.pct_change = 0)
    """
    c.execute(sql)
    conn.commit()
    print(f"  影响行数: {c.rowcount}")
    conn.close()
    print("完成")

if __name__ == "__main__":
    fix_pct()
