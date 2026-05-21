#!/bin/bash
# 🏠 Agent Chat 管理端启动 (macOS / Linux)

set -e
cd "$(dirname "$0")"

echo ""
echo "  🏠 Agent Chat - 管理端启动"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if ! command -v node &> /dev/null; then
  echo "❌ 请先安装 Node.js: https://nodejs.org"
  exit 1
fi

if [ ! -d "server/node_modules" ]; then
  echo "📦 安装依赖..."
  cd server && npm install && cd ..
fi

if [ ! -f "config.json" ]; then
  echo "⚠️  未找到 config.json，从模板创建..."
  cp config.example.json config.json
  echo "📝 请编辑 config.json 填入你的 API Key，然后重新运行"
  exit 1
fi

PORT=$(node -e "const c=require('./config.json'); console.log(c.serverPort||3000)")

echo "🧹 清理旧进程..."
lsof -ti:$PORT 2>/dev/null | xargs kill 2>/dev/null || true
sleep 1

echo "🚀 [1/3] 启动聊天服务器 (端口 $PORT)..."
node server/index.js &
sleep 2

if ! curl -s --max-time 3 http://localhost:$PORT/api/config > /dev/null 2>&1; then
  echo "❌ 服务器启动失败"
  exit 1
fi

echo "🤖 [2/3] 启动 AI Agent..."
node server/agent-bot.js &
sleep 2

echo "🌐 [3/3] 启动公网隧道..."
PUBLIC_URL=""

# 优先用 cloudflared（国内可直连）
if command -v cloudflared &> /dev/null; then
  echo "   使用 cloudflared..."
  cloudflared tunnel --url http://localhost:$PORT > /tmp/cloudflared.log 2>&1 &
  CF_PID=$!
  sleep 8
  PUBLIC_URL=$(cat /tmp/cloudflared.log 2>/dev/null | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1)
  if [ -n "$PUBLIC_URL" ]; then
    echo "   ✅ cloudflared 连接成功"
  else
    echo "   ⚠️ cloudflared 失败，尝试 ngrok..."
    kill $CF_PID 2>/dev/null
  fi
fi

# 回退到 ngrok
if [ -z "$PUBLIC_URL" ] && command -v ngrok &> /dev/null; then
  EXISTING=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{console.log(JSON.parse(d).tunnels[0].public_url)}catch{}})" 2>/dev/null || echo "")
  if [ -n "$EXISTING" ]; then
    PUBLIC_URL="$EXISTING"
  else
    ngrok http $PORT > /dev/null 2>&1 &
    sleep 5
    PUBLIC_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{console.log(JSON.parse(d).tunnels()[0].public_url)}catch{}})" 2>/dev/null || echo "")
  fi
fi

echo ""
echo "  ═══════════════════════════════════════"
echo "  ✅ 本地访问: http://localhost:$PORT"
if [ -n "$PUBLIC_URL" ]; then
  echo "  🌍 公网访问: $PUBLIC_URL"
  echo ""
  echo "  📋 同事 config.json 的 serverUrl:"
  echo "      wss://${PUBLIC_URL#https://}"
else
  echo "  💡 安装 cloudflared 获得公网地址:"
  echo "      https://github.com/cloudflare/cloudflared/releases"
fi
echo "  ═══════════════════════════════════════"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo ""

command -v open &> /dev/null && open "http://localhost:$PORT"
command -v xdg-open &> /dev/null && xdg-open "http://localhost:$PORT"

wait
