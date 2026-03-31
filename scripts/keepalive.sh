#!/bin/bash
# 服务守护脚本，每分钟检查一次，自动重启挂掉的服务
SERVICES=(
    "5001:python3:/root/.openclaw/workspace/stock_api.py:/root/.openclaw/workspace/stock_api.log"
    "5002:python3:/root/.openclaw/workspace/daily_updater.py:/root/.openclaw/workspace/daily_updater.log"
    "5000:python3:/root/.openclaw/workspace/bio_server.py:/root/.openclaw/workspace/bio_server.log"
)

for sv in "${SERVICES[@]}"; do
    IFS=':' read -r port prog path log <<< "$sv"
    if ! ss -tlnp | grep -q ":${port} " ; then
        echo "[$(date)] $port 重启中..."
        cd /root
        nohup python3 "$path" >> "$log" 2>&1 &
    fi
done
