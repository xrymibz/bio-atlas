#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回填股票行业分类数据（从东方财富数据中心）"""
import urllib.request, json, time, mysql.connector

DB_CONFIG = {
    "host": "localhost", "user": "root",
    "password": "OpenClaw@2026", "database": "a_stock_data"
}

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://data.eastmoney.com/"
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def get_industry_page(page):
    url = (f"https://datacenter-web.eastmoney.com/api/data/v1/get"
           f"?reportName=RPT_F10_BASIC_ORGINFO"
           f"&columns=SECURITY_CODE,SECURITY_NAME_ABBR,INDUSTRYCSRC1"
           f"&pageNumber={page}&pageSize=500"
           f"&sortColumns=SECURITY_CODE&sortTypes=1")
    txt = http_get(url)
    try:
        j = json.loads(txt)
        if j.get("success"):
            return j["result"]["data"], j["result"]["count"]
        print(f"  API失败: {j.get('message')}")
    except Exception as e:
        print(f"  解析失败: {e}, 内容: {txt[:200]}")
    return [], 0

def main():
    print("=" * 50)
    print("  股票行业数据回填")
    print("=" * 50)

    conn = get_db()
    c = conn.cursor()

    # 获取总数
    first_data, total = get_industry_page(1)
    if not first_data:
        print("无法获取数据，退出")
        return
    total = first_data[0].get("COUNT", total) if first_data else total
    pages = (total // 500) + 2
    print(f"  共 {total} 只股票，每页500，分 {pages} 页")

    updated = 0
    for page in range(1, pages + 1):
        print(f"  第 {page}/{pages} 页...", end="", flush=True)
        rows_data, _ = get_industry_page(page)
        if not rows_data:
            print(" 无数据")
            continue
        for item in rows_data:
            code = item.get("SECURITY_CODE", "")
            industry = item.get("INDUSTRYCSRC1", "") or ""
            # 格式 "金融业-货币金融服务" -> 取大类
            if industry and "-" in industry:
                sub_industry = industry.split("-", 1)[1]
                industry = industry.split("-", 1)[0]
            else:
                sub_industry = ""

            # 格式 ts_code: 000001 -> 000001.SZ 或 000001.SH
            if code:
                # 判断沪/深/北
                if code.startswith(("000", "001", "002", "003")) and len(code) == 6:
                    ts = code + ".SZ"
                elif code.startswith(("600", "601", "603", "605", "688")) and len(code) == 6:
                    ts = code + ".SH"
                elif code.startswith(("000", "001", "002", "003")) and len(code) == 6:
                    ts = code + ".SZ"
                elif code.startswith("4") or code.startswith("8"):
                    ts = code + ".BJ"
                else:
                    ts = code

                try:
                    c.execute("""
                        UPDATE stock_basic
                        SET industry=%s, sub_industry=%s
                        WHERE ts_code=%s OR symbol=%s
                    """, (industry, sub_industry, ts, code))
                except Exception as e:
                    pass

        conn.commit()
        print(f" ✅ {len(rows_data)} 只")
        updated += len(rows_data)
        time.sleep(0.3)  # 礼貌性延迟

    c.close()
    conn.close()
    print(f"\n🎉 完成！共更新 {updated} 只股票的行业信息")

if __name__ == "__main__":
    main()
