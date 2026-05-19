#!/bin/bash
# 🏠 Agent Chat 管理端启动脚本 (macOS / Linux)
# 启动：服务器 + AI Agent + 公网隧道

set -e
cd "$(dirname "$0")"

echo ""
echo "  🏠 Agent Chat - 管理端启动"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 检查 Node
if ! command -v node &> /dev/null; then
  echo "❌ 请先安装 Node.js: https://nodejs.org"
  exit 1
fi

# 安装依赖
if [ ! -d "server/node_modules" ]; then
  echo "📦 安装依赖..."
  cd server && npm install && cd ..
fi

# 检查配置
if [ ! -f "config.json" ]; then
  echo "⚠️  未找到 config.json，从模板创建..."
  cp config.example.json config.json
  echo "📝 请编辑 config.json 填入你的 API Key，然后重新运行"
  exit 1
fi

# 读取端口
PORT=$(node -e "const c=require('./config.json'); console.log(c.serverPort||3000)")

# 清理旧进程
echo "🧹 清理旧进程..."
lsof -ti:$PORT 2>/dev/null | xargs kill 2>/dev/null || true
pkill -f "node server/index.js" 2>/dev/null || true
pkill -f "node server/agent-bot.js" 2>/dev/null || true
sleep 1

# 启动聊天服务器
echo "🚀 [1/3] 启动聊天服务器 (端口 $PORT)..."
node server/index.js &
SERVER_PID=$!
sleep 2

# 检查服务器是否启动
if ! curl -s --max-time 3 http://localhost:$PORT/api/config > /dev/null 2>&1; then
  echo "❌ 服务器启动失败，请检查端口 $PORT 是否被占用"
  exit 1
fi

# 启动 AI Agent
echo "🤖 [2/3] 启动 AI Agent..."
node server/agent-bot.js &
BOT_PID=$!
sleep 2

# 启动公网隧道
echo "🌐 [3/3] 启动公网隧道..."
PUBLIC_URL=""

if command -v ngrok &> /dev/null; then
  # 先检查 ngrok 是否已在运行
  EXISTING=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{console.log(JSON.parse(d).tunnels[0].public_url)}catch{}})" 2>/dev/null || echo "")
  
  if [ -n "$EXISTING" ]; then
    PUBLIC_URL="$EXISTING"
    echo "   ✅ ngrok 已在运行"
  else
    ngrok http $PORT > /dev/null 2>&1 &
    sleep 5
    PUBLIC_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{console.log(JSON.parse(d).tunnels[0].public_url)}catch{}})" 2>/dev/null || echo "")
  fi
elif command -v cloudflared &> /dev/null; then
  cloudflared tunnel --url http://localhost:$PORT > /dev/null 2>&1 &
  sleep 8
  PUBLIC_URL=$(cat /tmp/cloudflared.log 2>/dev/null | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1 || echo "")
fi

echo ""
echo "  ═══════════════════════════════════════"
echo "  ✅ 本地访问: http://localhost:$PORT"

if [ -n "$PUBLIC_URL" ]; then
  echo "  🌍 公网访问: $PUBLIC_URL"
  echo ""
  echo "  📋 同事连接地址 (填入 config.json 的 serverUrl):"
  echo "      wss://${PUBLIC_URL#https://}"
else
  echo "  💡 安装 ngrok 获得公网地址: https://ngrok.com"
fi

echo "  ═══════════════════════════════════════"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo ""

# 打开浏览器
if command -v open &> /dev/null; then
  open "http://localhost:$PORT"
elif command -v xdg-open &> /dev/null; then
  xdg-open "http://localhost:$PORT"
fi

wait
