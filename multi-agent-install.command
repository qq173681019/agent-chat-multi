#!/bin/bash
# multi-agent-install.command — macOS Finder 双击安装
# 首次设置：创建 6 个 launchd plist + 加载

set -e
cd "$(dirname "$0")"

echo ""
echo "  🔧 Agent Chat Multi - 首次安装"
echo "  =============================="
echo ""

# 检查 secrets
SECRETS="$HOME/.agent-chat-secrets.json"
if [ ! -f "$SECRETS" ]; then
  echo "  [FAIL] $SECRETS 不存在"
  echo "  创建模板:"
  cat > "$SECRETS" << 'SECRETS_EOF'
{
  "apiKey": "你的智谱 API key",
  "apiBase": "https://open.bigmodel.cn/api/paas/v4/chat/completions"
}
SECRETS_EOF
  chmod 600 "$SECRETS"
  echo "  ✅ 已创建 $SECRETS，请填入你的 zhipu API key 后重跑此脚本"
  read -p "按回车关闭..."
  exit 1
fi

# 检查 agent-chat-multi 仓库
if [ ! -f "agents.json" ] || [ ! -d "server" ]; then
  echo "  [FAIL] 当前目录不是 agent-chat-multi 仓库"
  read -p "按回车关闭..."
  exit 1
fi

# 创建 6 个 plist (multi-agent 服务 + 5 个 agent bot)
SCRIPT_DIR="$(pwd)"
ZHIPU_KEY=$(python3 -c "
import json
with open('$SECRETS') as f:
    s = json.load(f)
print(s.get('apiKey', ''))
")

# === multi-agent 服务 plist ===
cat > "$HOME/Library/LaunchAgents/com.gongruolan.multi-agent.plist" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.gongruolan.multi-agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/node</string>
        <string>multi-agent.js</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}/server</string>
    <key>StandardOutPath</key>
    <string>/tmp/multi-agent-launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/multi-agent-launchd.err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
        <key>Crashed</key>
        <true/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
PLIST_EOF

# === 5 个 agent bot plist ===
for AGENT_ID in xiaodai hooligan merchant judge gossip; do
  cat > "$HOME/Library/LaunchAgents/com.gongruolan.multi-agent-bot-${AGENT_ID}.plist" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.gongruolan.multi-agent-bot-${AGENT_ID}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>-u</string>
        <string>${SCRIPT_DIR}/agent_poller.py</string>
        <string>${AGENT_ID}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ZHIPU_API_KEY</key>
        <string>${ZHIPU_KEY}</string>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/multi-agent-bot-${AGENT_ID}.out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/multi-agent-bot-${AGENT_ID}.err.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
        <key>Crashed</key>
        <true/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
PLIST_EOF
done

echo "  ✅ 6 个 plist 写好了"
echo ""
echo "  接下来："
echo "    1. 双击 multi-agent-start.command 启动"
echo "    2. 双击 multi-agent-stop.command 停止"
echo ""
read -p "按回车关闭此窗口..." || true
