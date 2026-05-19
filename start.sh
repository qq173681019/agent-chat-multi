#!/bin/bash
# Agent Chat 启动脚本 (macOS / Linux)

set -e
cd "$(dirname "$0")"

# 检查依赖
if ! command -v node &> /dev/null; then
  echo "❌ 请先安装 Node.js: https://nodejs.org"
  exit 1
fi

if [ ! -d "server/node_modules" ]; then
  echo "📦 安装依赖..."
  cd server && npm install && cd ..
fi

# 读取配置
PORT=$(node -e "const c=require('./config.json'); console.log(c.serverPort||3000)")

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   🤖 Agent Chat 启动中...            ║"
echo "╚══════════════════════════════════════╝"
echo ""

# 杀掉旧进程
lsof -ti:$PORT 2>/dev/null | xargs kill 2>/dev/null || true
sleep 1

# 启动服务器
echo "[1/3] 启动聊天服务器 (端口 $PORT)..."
node server/index.js &
SERVER_PID=$!
sleep 2

# 启动 Agent Bot
echo "[2/3] 启动 AI Agent..."
node server/agent-bot.js &
BOT_PID=$!
sleep 2

# 检查 ngrok
echo "[3/3] 检查公网隧道..."
PUBLIC_URL=""

if command -v ngrok &> /dev/null; then
  # 检查 ngrok 是否已在运行
  NGROK_STATUS=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null || echo "")
  if echo "$NGROK_STATUS" | grep -q "public_url"; then
    PUBLIC_URL=$(echo "$NGROK_STATUS" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>console.log(JSON.parse(d).tunnels[0].public_url))" 2>/dev/null)
    echo "   ngrok 已在运行"
  else
    ngrok http $PORT > /dev/null 2>&1 &
    sleep 5
    PUBLIC_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>console.log(JSON.parse(d).tunnels[0].public_url))" 2>/dev/null || echo "")
  fi
fi

echo ""
echo "══════════════════════════════════════"
echo "  ✅ 本地访问: http://localhost:$PORT"
if [ -n "$PUBLIC_URL" ]; then
  echo "  🌍 公网访问: $PUBLIC_URL"
fi
echo "══════════════════════════════════════"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 等待
wait
