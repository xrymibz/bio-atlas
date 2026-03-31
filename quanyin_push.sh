#!/bin/bash
# 荃银高科每日新闻分析推送脚本
# 由cron在每天9:00触发
# 写入待推送内容，heartbeat检测到后进行推送

PENDING_FILE="/root/.openclaw/workspace/quanyin_pending.txt"
ANALYSIS_FILE="/root/.openclaw/workspace/quanyin_analysis.json"

# 生成分析
python3 /root/.openclaw/workspace/quanyin_daily_analysis.py > "$PENDING_FILE" 2>/dev/null

# 标记时间
echo "GENERATED_AT=$(date +%Y-%m-%d\ %H:%M:%S)" >> "$PENDING_FILE"

echo "Analysis generated at $(date)" >> /root/.openclaw/workspace/quanyin_cron.log
