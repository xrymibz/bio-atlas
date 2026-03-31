#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
荃银高科每日新闻分析推送
每天早上9:00推送到微信
"""

import json, subprocess, sys
from datetime import datetime, timedelta

STOCK_CODE = "300087"
STOCK_NAME = "荃银高科"

def fetch_notices():
    import urllib.request
    url = f"https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_index=1&page_size=20&ann_type=SHA%2CCYB%2CSZA%2CBJA&client_source=web&stock_list={STOCK_CODE}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
            items = []
            for item in d.get("data", {}).get("list", [])[:20]:
                items.append({
                    "date": item.get("notice_date", "")[:10],
                    "title": item.get("title_ch", ""),
                    "category": item["columns"][0]["column_name"] if item.get("columns") else ""
                })
            return items
    except Exception as e:
        return []

def fetch_news():
    import urllib.request, re
    keyword = "荃银高科"
    encoded_kw = urllib.parse.quote(keyword)
    url = f"https://search-api-web.eastmoney.com/search/jsonp?cb=datad&param=%7B%22uid%22%3A%22%22%2C%22keyword%22%3A%22{encoded_kw}%22%2C%22type%22%3A%5B%22cmsArticle%22%5D%2C%22pageindex%22%3A1%2C%22pagesize%22%3A20%2C%22dfcfs%22%3A%220%22%2C%22executor%22%3A%22%22%2C%22searchScope%22%3A%22default%22%2C%22sort%22%3A%22default%22%2C%22dateTime%22%3A2%7D"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode("utf-8")
            m = re.search(r'datad\((.*)\)', raw, re.DOTALL)
            if not m:
                return []
            d = json.loads(m.group(1))
            items = []
            for item in d.get("result", {}).get("cmsArticle", [])[:20]:
                title = re.sub(r'<[^>]+>', '', item.get("title", ""))
                items.append({
                    "date": item.get("date", "")[:10],
                    "title": title,
                    "media": item.get("mediaName", "")
                })
            return items
    except Exception as e:
        return []

# ── 分析归类函数 ──────────────────────────────────
# 利好关键词
BULLISH_KEYWORDS = [
    "回购", "增持", "战略合作", "中标", "订单", "扩产", "技术突破",
    "业绩增长", "净利润增长", "营收增长", "分红", "高送转", "研发",
    "转基因", "种子", "一号文件", "农业", "丰收", "政策扶持", "涨停",
    "主力净流入", "获融资买入", "净买入"
]
# 利空关键词
BEARISH_KEYWORDS = [
    "减持", "亏损", "业绩下滑", "营收下降", "处罚", "立案", "警示函",
    "问询函", "调查", "风险提示", "跌停", "主力净流出", "净偿还",
    "涉嫌", "违规", "会计差错", "更正"
]

def is_bullish(text):
    text = text.lower()
    for kw in BULLISH_KEYWORDS:
        if kw in text:
            return True
    return False

def is_bearish(text):
    text = text.lower()
    for kw in BEARISH_KEYWORDS:
        if kw in text:
            return True
    return False

def judge_impact(text, category=""):
    """
    判断对股价的影响:
    - return: "long_bullish" | "long_bearish" | "short_bullish" | "short_bearish"
    """
    # 重大负面 → 长期利空
    if any(k in text for k in ["立案", "调查", "处罚", "涉嫌违法违规", "会计差错更正（重大）", "虚假陈述"]):
        return "long_bearish"
    # 高管减持计划/到期 → 短期利空
    if "减持" in text:
        return "short_bearish"
    # 会计差错更正（一般）→ 短期利空（情绪）
    if "会计差错更正" in text or "会计差错" in text:
        return "short_bearish"
    # 回购/增持 → 短期+长期利好
    if any(k in text for k in ["回购", "增持", "战略合作", "中标", "签订合同"]):
        return "long_bullish"
    # 融资净买入/主力净流入 → 短期利好
    if any(k in text for k in ["融资净买入", "主力净流入", "净买入"]):
        return "short_bullish"
    # 融资净偿还/主力净流出 → 短期利空
    if any(k in text for k in ["融资净偿还", "主力净流出", "净偿还"]):
        return "short_bearish"
    # 业绩/基本面改善 → 长期利好
    if any(k in text for k in ["净利润增长", "营收增长", "业绩增长", "订单", "扩产"]):
        return "long_bullish"
    # 板块/概念上涨（行业）→ 短期利好
    if any(k in text for k in ["涨停", "涨幅达", "快速上涨", "概念上涨", "资金净流入"]):
        return "short_bullish"
    # 跌幅/下跌 → 短期利空
    if any(k in text for k in ["跌幅达", "下跌", "跌停"]):
        return "short_bearish"
    # 董事会换届/工商变更 → 中性，略正面（治理改善预期）
    if any(k in text for k in ["董事会换届", "法定代表人变更", "高管任职"]):
        return "short_bullish"
    return "neutral"

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    notices = fetch_notices()
    news = fetch_news()

    # 过滤最近3天内的内容
    recent_notices = [n for n in notices if n["date"] >= yesterday]
    recent_news = [n for n in news if n["date"] >= yesterday]

    buckets = {
        "long_bullish":  [],
        "long_bearish":  [],
        "short_bullish": [],
        "short_bearish": []
    }

    for n in recent_notices + recent_news:
        text = n["title"]
        impact = judge_impact(text, n.get("category",""))
        source = f"【公告】{n['date']}" if n.get("category") else f"【资讯】{n['date']}"
        entry = f"{source} {text}"
        if impact in buckets:
            buckets[impact].append(entry)

    # ── 渲染消息 ──────────────────────────────────
    lines = []
    lines.append(f"📰 {STOCK_NAME}({STOCK_CODE}) 每日新闻分析")
    lines.append(f"📅 {today} 早间推送\n")

    sections = [
        ("🌟 长期利好", "long_bullish"),
        ("💥 长期利空", "long_bearish"),
        ("⏰ 短期利好", "short_bullish"),
        ("⚠️ 短期利空", "short_bearish"),
    ]
    has_content = False
    for label, key in sections:
        items = buckets[key]
        if items:
            has_content = True
            lines.append(f"{label}（{len(items)}条）")
            for item in items:
                lines.append(f"  • {item}")
            lines.append("")

    if not has_content:
        lines.append("📢 今日暂无重要新闻更新。")

    lines.append("───")
    lines.append("⚠️ 免责声明：以上分析仅供参考，不构成投资建议。")

    msg = "\n".join(lines)
    print(msg)
    return msg

if __name__ == "__main__":
    main()
