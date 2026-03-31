#!/bin/bash
# 检查是否需要推送荃银高科每日分析
# 由heartbeat调用，或由cron直接调用

PENDING_FILE="/root/.openclaw/workspace/quanyin_pending.txt"
LAST_PUSH_FILE="/root/.openclaw/workspace/quanyin_last_push_date.txt"
ANALYSIS_SCRIPT="/root/.openclaw/workspace/quanyin_daily_analysis.py"

TODAY=$(date +%Y-%m-%d)
LAST_PUSH=""
if [ -f "$LAST_PUSH_FILE" ]; then
    LAST_PUSH=$(cat "$LAST_PUSH_FILE")
fi

# 如果今天已经推送过，跳过
if [ "$LAST_PUSH" = "$TODAY" ]; then
    echo "Already pushed today ($TODAY)"
    exit 0
fi

# 生成今日分析
python3 "$ANALYSIS_SCRIPT" > "$PENDING_FILE" 2>/dev/null

# 标记推送时间
echo "$TODAY" > "$LAST_PUSH_FILE"

echo "Analysis ready for $TODAY"
cat "$PENDING_FILE"
