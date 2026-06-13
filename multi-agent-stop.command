#!/bin/bash
# Agent Chat Multi - One Key Stop (macOS Finder 双击)
# 等价于 windows 的 stop-all.bat
# 功能: 停 server (端口 3001) + 停 cloudflared + 清理 .pid 文件

BASEDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASEDIR"

echo ""
echo "  ══ Agent Chat Multi - 一键停止 (Mac) ══"
echo "  ════════════════════════════════════════"
echo ""

# 读端口
PORT=3001
if [ -f "agents.json" ]; then
  PORT=$(node -e "const c=require('./agents.json'); console.log(c.serverPort||3001)" 2>/dev/null || echo "3001")
fi

# ── 1. 停 server (端口) ──
# 2026-06-13 16:43: 用 xargs 处理 lsof 多行 PID (5 bot plist + server 共享 3001)
echo "  [1/3] 停止 multi-agent 服务 (端口 $PORT)..."
PIDS=$(lsof -ti:$PORT 2>/dev/null | tr '\n' ' ' | xargs)
if [ -n "$PIDS" ]; then
  echo "$PIDS" | xargs kill 2>/dev/null
  sleep 1
  PIDS2=$(lsof -ti:$PORT 2>/dev/null | tr '\n' ' ' | xargs)
  [ -n "$PIDS2" ] && echo "$PIDS2" | xargs kill -9 2>/dev/null
  echo "  ✅ 已停 node (端口 $PORT, PIDs: $PIDS)"
else
  echo "  （端口 $PORT 没人占, skip）"
fi

# ── 2. 停 cloudflared ──
echo "  [2/3] 停止 cloudflared 隧道..."
if pgrep -f "cloudflared tunnel" > /dev/null; then
  pkill -f "cloudflared tunnel" 2>/dev/null
  echo "  ✅ 已停 cloudflared"
else
  echo "  （cloudflared 没在跑, skip）"
fi

# ── 3. 清理遗留 .pid 文件 ──
echo "  [3/3] 清理 .pid 文件..."
CLEANED=0
for f in .pids.json .server.pid .poller_*.pid; do
  if [ -f "$f" ]; then
    rm -f "$f"
    CLEANED=$((CLEANED + 1))
  fi
done
[ $CLEANED -gt 0 ] && echo "  ✅ 清理 $CLEANED 个 .pid" || echo "  （无遗留 .pid, skip）"

echo ""
echo "  ════════════════════════════════════════"
echo "  ✅ 全部已停"
echo "  ════════════════════════════════════════"
echo ""
echo "  按任意键关闭..."
read -n 1
