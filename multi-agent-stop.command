#!/bin/bash
# multi-agent-stop.command — macOS Finder 双击停止
# 停止 multi-agent 服务 + 5 个 agent poller (launchd unload)

echo ""
echo "  🛑 Agent Chat Multi - 一键停止"
echo "  =============================="
echo ""

LAUNCH_AGENTS=(
  "$HOME/Library/LaunchAgents/com.gongruolan.multi-agent.plist"
  "$HOME/Library/LaunchAgents/com.gongruolan.multi-agent-bot-xiaodai.plist"
  "$HOME/Library/LaunchAgents/com.gongruolan.multi-agent-bot-hooligan.plist"
  "$HOME/Library/LaunchAgents/com.gongruolan.multi-agent-bot-merchant.plist"
  "$HOME/Library/LaunchAgents/com.gongruolan.multi-agent-bot-judge.plist"
  "$HOME/Library/LaunchAgents/com.gongruolan.multi-agent-bot-gossip.plist"
)

for PLIST in "${LAUNCH_AGENTS[@]}"; do
  if [ -f "$PLIST" ]; then
    NAME=$(basename "$PLIST" .plist)
    launchctl unload "$PLIST" 2>/dev/null
    echo "  ✅ 停止 $NAME"
  fi
done

# 兜底：手动 kill
echo ""
echo "  兜底 kill 所有残留进程..."
pkill -f "node multi-agent.js" 2>/dev/null && echo "  ✅ 杀了 multi-agent.js" || echo "  ⏭️  无 multi-agent.js 残留"
pkill -f "agent_poller.py" 2>/dev/null && echo "  ✅ 杀了 agent_poller.py" || echo "  ⏭️  无 agent_poller.py 残留"

# 验证
echo ""
sleep 2
SERVER_PID=$(lsof -ti:3001 2>/dev/null | head -1)
if [ -n "$SERVER_PID" ]; then
  echo "  ⚠️  port 3001 还在被 PID $SERVER_PID 占用，kill -9 ..."
  kill -9 $SERVER_PID
fi
echo ""
echo "  ====================================="
echo "  ✅ 全部停止"
echo "  ====================================="
echo ""
read -p "按回车关闭此窗口..." || true
