#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日趋势金叉报告生成 & 推送"""
import urllib.request, json, datetime, sys

def get_report():
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:5001/api/strategy/golden_cross?top=10",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"API调用失败: {e}")
        return None

def format_report(d):
    items = d["data"]["items"]
    date = d["data"]["trade_date"]
    total = d["data"]["total"]
    lines = []
    lines.append("📈 趋势跟进金叉信号")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📅 {date} | 共 **{total} 只**通过严格筛选")
    lines.append("")
    for it in items:
        vol = it.get("vol_ratio", 0)
        pct3m = it.get("pct_3m", 0)
        cross = it.get("cross_strength", 0)
        close = it.get("close", "-")
        name = it.get("name", "")
        code = it.get("ts_code", "")
        if it.get("low_3m"):
            pos = f"近3月 {pct3m:.1f}%"
            badge = "🔴"
        else:
            pos = "横盘整理"
            badge = "🟡"
        lines.append(f"{badge} **{name}** {code}")
        lines.append(f"   收盘 {close} | 量比 {vol}x | {pos}")
        lines.append(f"   金叉 +{cross:.2f}%")
        lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ 仅供参考，不构成投资建议")
    return "\n".join(lines)

if __name__ == "__main__":
    d = get_report()
    if d:
        text = format_report(d)
        print(text)
        with open("/root/.openclaw/workspace/golden_cross_report.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 报告已生成并保存")
    else:
        sys.exit(1)
