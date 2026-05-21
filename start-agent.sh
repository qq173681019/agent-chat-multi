#!/bin/bash
# 🤖 Agent Chat 使用端启动脚本 (macOS / Linux)
# 只启动 AI Agent，连接到管理端服务器

set -e
cd "$(dirname "$0")"

echo ""
echo "  🤖 Agent Chat - 使用端启动"
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
  echo "⚠️  未找到 config.json"
  echo ""
  echo "请创建 config.json，模板如下："
  echo ""
  cat << 'EXAMPLE'
{
  "botName": "你的机器人名字",
  "botRole": "agent-b",
  "serverUrl": "wss://管理端的ngrok地址",
  "apiKey": "你的API Key",
  "apiBase": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
  "model": "glm-4-flash",
  "useProxy": false,
  "serverPort": 3000
}
EXAMPLE
  echo ""
  echo "关键："
  echo "  - serverUrl 填管理端给你的 wss:// 地址"
  echo "  - botRole 必须是 agent-b（避免和管理端冲突）"
  echo "  - apiKey 填你自己的 API Key"
  exit 1
fi

# 显示配置
BOT_NAME=$(node -e "const c=require('./config.json'); console.log(c.botName||'Agent')")
BOT_ROLE=$(node -e "const c=require('./config.json'); console.log(c.botRole||'agent-b')")
SERVER=$(node -e "const c=require('./config.json'); console.log(c.serverUrl||'未配置')")

echo "  机器人名字: $BOT_NAME"
echo "  角色: $BOT_ROLE"
echo "  连接地址: $SERVER"
echo ""

if [ "$SERVER" = "未配置" ]; then
  echo "❌ serverUrl 未配置！请填入管理端的 wss:// 地址"
  exit 1
fi

echo "🚀 启动 AI Agent..."
echo ""
node server/agent-bot.js
