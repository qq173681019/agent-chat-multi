#!/bin/bash
# Agent Chat Multi - One Key Start (macOS / Linux)
set -e
cd "$(dirname "$0")"

echo ""
echo "  🤖 Agent Chat Multi - One Key Start"
echo "  ====================================="
echo ""

# ── 0. 环境检查 ──
if ! command -v node &> /dev/null; then
  echo "  [FAIL] Please install Node.js: https://nodejs.org"
  exit 1
fi

if [ ! -d "server/node_modules" ]; then
  echo "  [1/5] Installing dependencies..."
  (cd server && npm install)
  echo "  [OK] Dependencies installed"
else
  echo "  [1/5] Dependencies OK"
fi

# ── 0b. agents.json 检查（multi-agent 服务的真实配置）──
if [ ! -f "agents.json" ]; then
  echo "  [FAIL] agents.json not found!"
  echo "         multi-agent 服务用 agents.json 加载 agent 角色配置"
  exit 1
fi

PORT=$(node -e "const c=require('./agents.json'); console.log(c.serverPort||3001)" 2>/dev/null || echo "3001")
echo "  Config OK, using port: $PORT"

# ── 1. 清理旧进程 ──
echo "  [2/5] Cleaning old processes..."
PID=$(lsof -ti:$PORT 2>/dev/null || true)
[ -n "$PID" ] && kill -9 $PID 2>/dev/null
WAITED=0
while [ $WAITED -lt 10 ]; do
  LISTENING=$(lsof -ti:$PORT 2>/dev/null || true)
  if [ -z "$LISTENING" ]; then
    break
  fi
  sleep 1
  WAITED=$((WAITED + 1))
done
echo "  [OK] Cleaned port $PORT"

# ── 2. 启动 multi-agent 服务 ──
echo "  [3/5] Starting multi-agent server on port $PORT..."
cd server
nohup node multi-agent.js > /tmp/multi-agent-$PORT.log 2>&1 &
SERVER_PID=$!
cd ..
sleep 3

if ! curl -s --max-time 3 "http://localhost:$PORT/api/config" > /dev/null 2>&1; then
  echo "  [FAIL] Server not responding on port $PORT!"
  echo "  Check /tmp/multi-agent-$PORT.log"
  exit 1
fi
echo "  [OK] Server ready (PID $SERVER_PID)"

# ── 3. 检查 cloudflared 隧道 ──
echo "  [4/5] Checking cloudflared tunnel..."

CF_TOKEN_FILE="$HOME/.cloudflared/agent-chat-token"
if [ ! -f "$CF_TOKEN_FILE" ]; then
  echo "  [WARN] No tunnel token at $CF_TOKEN_FILE"
  echo "         Local works, but https://multi.agent-chat.org won't."
  echo "         See agent-chat repo DNS-SETUP.md for one-time setup."
else
  if pgrep -f "cloudflared tunnel run" > /dev/null; then
    echo "  [OK] Cloudflared tunnel already running"
  else
    CF_TOKEN=$(cat "$CF_TOKEN_FILE")
    nohup cloudflared tunnel run --token "$CF_TOKEN" > "$HOME/.cloudflared/multi-agent.log" 2>&1 &
    echo "  [OK] Started cloudflared tunnel (PID $!)"
  fi
fi

# ── 4. 验证公网 ──
echo "  [5/5] Verifying https://multi.agent-chat.org ..."
VERIFY_OK=0
for i in $(seq 1 10); do
  if curl -s --max-time 5 "https://multi.agent-chat.org/api/config" > /dev/null 2>&1; then
    VERIFY_OK=1
    break
  fi
  sleep 2
done

# ── 5. 总结 ──
echo ""
echo "  ====================================="
if [ "$VERIFY_OK" = "1" ]; then
  echo "  ✅ All systems go!"
  echo "  🌐 Public:  https://multi.agent-chat.org"
else
  echo "  ⚠️  Local works, but public domain not yet reachable."
  echo "      Check Cloudflare Dashboard → Published application routes"
fi
echo "  🏠 Local:   http://localhost:$PORT"
echo "  📋 Logs:    /tmp/multi-agent-$PORT.log"
echo "              $HOME/.cloudflared/multi-agent.log"
echo "  ====================================="
echo ""

# 打开浏览器
command -v open &> /dev/null && open 'https://multi.agent-chat.org'
command -v xdg-open &> /dev/null && xdg-open 'https://multi.agent-chat.org'

