#!/bin/bash
# 隧道守护脚本：每 60 秒检测隧道是否存活，断了自动重启并更新地址
# 用法: screen -dmS tunnel-watch bash ~/agent-chat/watch-tunnel.sh

LOG="/tmp/tunnel-watch.log"
INTERVAL=60

log() { echo "[$(date '+%H:%M:%S')] $1" >> "$LOG"; }

while true; do
    # 获取当前隧道地址
    CURRENT_URL=$(strings /tmp/cloudflared.log 2>/dev/null | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1)
    
    if [ -z "$CURRENT_URL" ]; then
        log "⚠️ 没有隧道地址，重启 cloudflared..."
        screen -S cloudflared -X quit 2>/dev/null
        pkill -f cloudflared 2>/dev/null
        sleep 3
        screen -dmS cloudflared bash -c 'cloudflared tunnel --url http://localhost:3000 > /tmp/cloudflared.log 2>&1'
        sleep 10
        NEW_URL=$(strings /tmp/cloudflared.log 2>/dev/null | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1)
        if [ -n "$NEW_URL" ]; then
            log "✅ 新隧道: $NEW_URL"
            ~/agent-chat/update-tunnel-url.sh "$NEW_URL" >> "$LOG" 2>&1
        else
            log "❌ 重启失败，等下一轮重试"
        fi
        sleep $INTERVAL
        continue
    fi
    
    # 测试隧道是否通
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 --proxy http://127.0.0.1:7897 "$CURRENT_URL/api/config" 2>/dev/null)
    
    if [ "$HTTP_CODE" = "200" ]; then
        # 隧道正常，静默
        :
    else
        log "⚠️ 隧道不通 (HTTP $HTTP_CODE)，重启..."
        screen -S cloudflared -X quit 2>/dev/null
        pkill -f cloudflared 2>/dev/null
        sleep 3
        screen -dmS cloudflared bash -c 'cloudflared tunnel --url http://localhost:3000 > /tmp/cloudflared.log 2>&1'
        sleep 10
        NEW_URL=$(strings /tmp/cloudflared.log 2>/dev/null | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1)
        if [ -n "$NEW_URL" ]; then
            log "✅ 新隧道: $NEW_URL"
            ~/agent-chat/update-tunnel-url.sh "$NEW_URL" >> "$LOG" 2>&1
        else
            log "❌ 重启失败，等下一轮重试"
        fi
    fi
    
    sleep $INTERVAL
done
