#!/bin/bash
# Agent Chat Multi - One Key Start (macOS Finder 双击)
# 等价于 windows 的 start-all.bat + multi-agent-start.sh
# 功能: 安装依赖 + 启 server + 检查 cloudflared 隧道 + 验证公网 + 开浏览器

BASEDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASEDIR"

echo ""
echo "  ══ Agent Chat Multi - 一键启动 (Mac) ══"
echo "  ════════════════════════════════════════"
echo ""

# ── 0. 环境检查 ──
if ! command -v node &> /dev/null; then
  echo "  ❌ 请先安装 Node.js: https://nodejs.org"
  echo ""
  echo "  按任意键关闭..."
  read -n 1
  exit 1
fi

# ── 1. 装依赖 ──
echo "  [1/5] 检查依赖..."
if [ ! -d "server/node_modules" ]; then
  echo "  📦 首次安装依赖..."
  (cd server && npm install) || {
    echo "  ❌ npm install 失败"
    echo ""
    echo "  按任意键关闭..."
    read -n 1
    exit 1
  }
fi
echo "  ✅ 依赖就绪"

# ── 2. 读 agents.json (server port) ──
if [ ! -f "agents.json" ]; then
  echo "  ❌ agents.json 不存在!"
  echo "     multi-agent 服务用 agents.json 加载 agent 角色配置"
  echo ""
  echo "  按任意键关闭..."
  read -n 1
  exit 1
fi

PORT=$(node -e "const c=require('./agents.json'); console.log(c.serverPort||3001)" 2>/dev/null || echo "3001")
echo "  📡 配置端口: $PORT"

# ── 3. 清旧进程 ──
echo "  [2/5] 清理旧进程 (端口 $PORT)..."
PID=$(lsof -ti:$PORT 2>/dev/null || true)
[ -n "$PID" ] && kill -9 $PID 2>/dev/null
WAITED=0
while [ $WAITED -lt 10 ]; do
  LISTENING=$(lsof -ti:$PORT 2>/dev/null || true)
  if [ -z "$LISTENING" ]; then break; fi
  sleep 1
  WAITED=$((WAITED + 1))
done
echo "  ✅ 端口 $PORT 已清理"

# ── 4. 启 server ──
echo "  [3/5] 启动 multi-agent 服务 (端口 $PORT)..."
cd "$BASEDIR/server"
nohup node multi-agent.js > /tmp/multi-agent-$PORT.log 2>&1 &
SERVER_PID=$!
cd "$BASEDIR"
sleep 3

if ! curl -s --max-time 3 "http://localhost:$PORT/api/config" > /dev/null 2>&1; then
  echo "  ❌ Server 启动失败! 看 /tmp/multi-agent-$PORT.log"
  echo ""
  echo "  按任意键关闭..."
  read -n 1
  exit 1
fi
echo "  ✅ Server 就绪 (PID $SERVER_PID)"

# ── 5. cloudflared 隧道 ──
echo "  [4/5] 检查 cloudflared 隧道..."
CF_TOKEN_FILE="$HOME/.cloudflared/agent-chat-token"
if [ ! -f "$CF_TOKEN_FILE" ]; then
  echo "  ⚠️  找不到 $CF_TOKEN_FILE"
  echo "     本地能用, 但 https://multi.agent-chat.org 不行"
  echo "     见 agent-chat 仓 DNS-SETUP.md 一次性配置"
else
  if pgrep -f "cloudflared tunnel" > /dev/null; then
    echo "  ✅ cloudflared 隧道已在跑"
  else
    CF_TOKEN=$(cat "$CF_TOKEN_FILE")
    nohup cloudflared tunnel run --token "$CF_TOKEN" > "$HOME/.cloudflared/multi-agent.log" 2>&1 &
    echo "  ✅ cloudflared 启动 (PID $!)"
  fi
fi

# ── 6. 验证公网 ──
echo "  [5/5] 验证 https://multi.agent-chat.org ..."
VERIFY_OK=0
for i in $(seq 1 10); do
  if curl -s --max-time 5 "https://multi.agent-chat.org/api/config" > /dev/null 2>&1; then
    VERIFY_OK=1
    break
  fi
  sleep 2
done

# ── 7. 总结 ──
echo ""
echo "  ════════════════════════════════════════"
if [ "$VERIFY_OK" = "1" ]; then
  echo "  ✅ 全部就绪!"
  echo "  🌐 公网:   https://multi.agent-chat.org"
  PUBLIC_URL="https://multi.agent-chat.org"
else
  echo "  ⚠️  本地 OK, 公网域名还没通"
  echo "      看 Cloudflare Dashboard → Published application routes"
  PUBLIC_URL="http://localhost:$PORT"
fi
echo "  🏠 本地:   http://localhost:$PORT"
echo "  📋 日志:   /tmp/multi-agent-$PORT.log"
echo "             $HOME/.cloudflared/multi-agent.log"
echo "  ════════════════════════════════════════"
echo ""
echo "  打开浏览器..."
command -v open &> /dev/null && open "$PUBLIC_URL"

echo ""
echo "  ──────────────────────────────────────"
echo "  💡 服务在后台跑, 关闭这个窗口不影响"
echo "  💡 停止服务请双击 multi-agent-stop.command"
echo "  按任意键关闭此窗口..."
read -n 1
