#!/bin/bash
cd /root

# 调用API获取金叉数据
RESULT=$(curl -s "http://127.0.0.1:5001/api/strategy/golden_cross?top=10")
TOTAL=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['total'])")
echo "$RESULT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
items = d['data']['items']
date = d['data']['trade_date']
total = d['data']['total']
lines = []
lines.append('📈 趋势跟进金叉信号（每日7:00自动推送）')
lines.append('━━━━━━━━━━━━━━━━━━━━')
lines.append('📅 %s 收盘 | 共 **%s 只**通过严格筛选' % (date, total))
for it in items:
    vol = it.get('vol_ratio', 0)
    pct3m = it.get('pct_3m', 0)
    cross = it.get('cross_strength', 0)
    close = it.get('close', '-')
    name = it.get('name', '')
    code = it.get('ts_code', '')
    if it.get('low_3m'):
        pos = '近3月 %.1f%%' % pct3m
        badge = '🔴'
    else:
        pos = '横盘整理'
        badge = '🟡'
    lines.append('')
    lines.append('%s **%s** %s' % (badge, name, code))
    lines.append('   收盘 %s | 量比 %sx | %s' % (close, vol, pos))
    lines.append('   金叉强度 +%.2f%%' % cross)
lines.append('━━━━━━━━━━━━━━━━━━━━')
lines.append('⚠️ 仅供参考，不构成投资建议')
print('\n'.join(lines))
" > /root/.openclaw/workspace/golden_cross_report.txt

echo "✅ 报告已生成 $(date)"