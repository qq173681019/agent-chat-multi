#!/bin/bash
# multi-agent-start.command — macOS Finder 双击启动
# 启动 multi-agent 服务 + 5 个 agent poller (全程 launchd 守护)

set -e
cd "$(dirname "$0")"

echo ""
echo "  🤖 Agent Chat Multi - 一键启动"
echo "  =============================="
echo ""

# === 检查依赖 ===
if ! command -v node &> /dev/null; then
  echo "  [FAIL] Node.js 未安装: https://nodejs.org"
  read -p "按回车关闭..."
  exit 1
fi
if [ ! -d "server/node_modules" ]; then
  echo "  [1/6] 安装 server 依赖..."
  (cd server && npm install)
fi

# === 检查 agents.json ===
if [ ! -f "agents.json" ]; then
  echo "  [FAIL] agents.json 不存在"
  read -p "按回车关闭..."
  exit 1
fi
echo "  [1/6] Config OK (agents.json 已读)"

# === 加载 6 个 launchd 任务（multi-agent 服务 + 5 个 agent bot）===
echo "  [2/6] 加载 launchd 任务..."

LAUNCH_AGENTS=(
  "$HOME/Library/LaunchAgents/com.gongruolan.multi-agent.plist"
  "$HOME/Library/LaunchAgents/com.gongruolan.multi-agent-bot-xiaodai.plist"
  "$HOME/Library/LaunchAgents/com.gongruolan.multi-agent-bot-hooligan.plist"
  "$HOME/Library/LaunchAgents/com.gongruolan.multi-agent-bot-merchant.plist"
  "$HOME/Library/LaunchAgents/com.gongruolan.multi-agent-bot-judge.plist"
  "$HOME/Library/LaunchAgents/com.gongruolan.multi-agent-bot-gossip.plist"
)

for PLIST in "${LAUNCH_AGENTS[@]}"; do
  if [ ! -f "$PLIST" ]; then
    echo "  [FAIL] 缺失 plist: $PLIST"
    echo "  请先用 multi-agent-install.sh 安装"
    read -p "按回车关闭..."
    exit 1
  fi
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
done

# === 检查 cloudflared 隧道（可选）===
echo "  [3/6] 检查 cloudflared 隧道..."
if pgrep -f "cloudflared.*tunnel.*--config" > /dev/null; then
  echo "  ✅ cloudflared 已在跑"
else
  echo "  ⚠️  cloudflared 没在跑（需要单独启动才能用公网 https://multi.agent-chat.org）"
  echo "     启动: cloudflared tunnel --config ~/.cloudflared/机器人花园.yml run 机器人花园 &"
fi

# === 等 5 秒，让服务 + agent 全连上 ===
echo "  [4/6] 等 5 秒让服务启动..."
sleep 5

# === 验证 ===
echo "  [5/6] 验证服务..."
SERVER_PID=$(lsof -ti:3001 2>/dev/null | head -1)
if [ -n "$SERVER_PID" ]; then
  echo "  ✅ multi-agent 服务: PID $SERVER_PID (port 3001)"
else
  echo "  ❌ multi-agent 服务没起来，看日志: tail /tmp/multi-agent-launchd.err.log"
fi

ONLINE_COUNT=$(curl -s https://multi.agent-chat.org/api/agents 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(sum(1 for a in data['agents'] if a.get('online')))
except:
    print('?')
")
TOTAL_COUNT=$(curl -s https://multi.agent-chat.org/api/agents 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(len(data['agents']))
except:
    print('?')
")
echo "  ✅ Agent 在线: $ONLINE_COUNT / $TOTAL_COUNT"

echo "  [6/6] 验证公网..."
HTTP_CODE=$(curl -s -o /dev/null -m 5 -w "%{http_code}" https://multi.agent-chat.org/api/config 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
  echo "  ✅ https://multi.agent-chat.org: HTTP $HTTP_CODE"
else
  echo "  ⚠️  公网: HTTP $HTTP_CODE (cloudflared 没起 or 域名问题)"
fi

echo ""
echo "  ====================================="
echo "  ✅ 启动完成！"
echo "  🌐 本地: http://localhost:3001"
echo "  🌐 公网: https://multi.agent-chat.org"
echo ""
echo "  关闭: 双击 multi-agent-stop.command"
echo "  日志: tail -f /tmp/multi-agent-launchd.out.log"
echo "        tail -f /tmp/multi-agent-bot-*.out.log"
echo "  ====================================="
echo ""
read -p "按回车关闭此窗口..." || true
