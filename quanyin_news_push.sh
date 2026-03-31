#!/bin/bash
# 荃银高科每日新闻分析推送
# 每天早上9:00推送

MX_APIKEY="${MX_APIKEY}"
TODAY=$(date +%Y-%m-%d)
STOCK_CODE="300087"
STOCK_NAME="荃银高科"

# 1. 获取最新公告
NOTICES=$(curl -s "https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_index=1&page_size=10&ann_type=SHA%2CCYB%2CSZA%2CBJA&client_source=web&stock_list=${STOCK_CODE}" 2>/dev/null)

# 2. 获取最新快讯
NEWS_URL="https://search-api-web.eastmoney.com/search/jsonp?cb=datad&param=%7B%22uid%22%3A%22%22%2C%22keyword%22%3A%22%E8%8D%9F%E9%93%B6%E9%AB%98%E7%A7%91%22%2C%22type%22%3A%5B%22cmsArticle%22%5D%2C%22pageindex%22%3A1%2C%22pagesize%22%3A15%2C%22dfcfs%22%3A%220%22%2C%22executor%22%3A%22%22%2C%22searchScope%22%3A%22default%22%2C%22sort%22%3A%22default%22%2C%22dateTime%22%3A2%7D"
NEWS=$(curl -s "$NEWS_URL" 2>/dev/null)

echo "NOTICES_COUNT=$(echo "$NOTICES" | grep -o "notice_date" | wc -l)"
echo "NEWS_COUNT=$(echo "$NEWS" | grep -o "title" | wc -l)"
echo "===NOTICES==="
echo "$NOTICES" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for item in d['data']['list'][:10]:
    print(f\"【{item['notice_date'][:10]}】 {item['title_ch']} | {item['columns'][0]['column_name']}\")
" 2>/dev/null
echo "===NEWS==="
echo "$NEWS" | python3 -c "
import json,sys,re
raw = sys.stdin.read()
m = re.search(r'datad\((.*)\)', raw, re.DOTALL)
if m:
    d=json.loads(m.group(1))
    for item in d['result']['cmsArticle'][:15]:
        print(f\"【{item['date'][:10]}】 {item['title']} | {item['mediaName']}\")
" 2>/dev/null
