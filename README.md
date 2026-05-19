# 🤖 Agent Chat

一个轻量的 AI 聊天室，支持多人和多个 AI Agent 实时对话。

## 功能

- 💬 多人实时聊天（WebSocket）
- 🤖 多个 AI Agent 同时在线
- 💾 聊天记录导出/导入
- 📱 手机端适配
- ⚙️ 可配置机器人名字、模型、提示词
- 🖥️ macOS + Windows 双平台支持

## 快速开始

### 你的电脑（管理端）

管理端运行聊天服务器 + 你的 AI Agent。

**macOS / Linux：**
```bash
git clone https://github.com/qq173681019/agent-chat.git
cd agent-chat
cp config.example.json config.json
# 编辑 config.json 填入你的 API Key
bash start-host.sh
```

**Windows：**
```cmd
git clone https://github.com/qq173681019/agent-chat.git
cd agent-chat
copy config.example.json config.json
:: 编辑 config.json 填入你的 API Key
start-host.bat
```

启动后会显示：
- ✅ 本地访问地址
- 🌍 公网访问地址（需要 ngrok）
- 📋 **同事连接地址**（给同事用）

### 同事的电脑（使用端）

使用端只运行 AI Agent，连接到你的聊天服务器。

**macOS / Linux：**
```bash
git clone https://github.com/qq173681019/agent-chat.git
cd agent-chat
cp config.example.json config.json
# 编辑 config.json，关键配置：
#   botRole: "agent-b"
#   serverUrl: "wss://管理端给你的地址"
#   apiKey: "同事自己的API Key"
bash start-agent.sh
```

**Windows：**
```cmd
git clone https://github.com/qq173681019/agent-chat.git
cd agent-chat
copy config.example.json config.json
:: 编辑 config.json
start-agent.bat
```

## 配置说明

编辑 `config.json`：

| 字段 | 管理端 | 使用端 | 说明 |
|------|--------|--------|------|
| botName | ✅ | ✅ | 机器人显示名字 |
| botRole | agent-a | **agent-b** | 必须不同 |
| serverUrl | 留空 | **wss://地址** | 管理端ngrok地址 |
| apiKey | ✅ | ✅ | 各自的 API Key |
| apiBase | ✅ | ✅ | API 地址 |
| model | ✅ | ✅ | 模型名称 |
| useProxy | 按需 | 按需 | 是否用代理 |
| proxy | ✅ | ✅ | 代理地址 |
| serverPort | ✅ | 无需 | 服务端口（默认3000）|

## 项目结构

```
agent-chat/
├── config.json           # 配置文件（需自行创建）
├── config.example.json   # 配置模板
├── server/
│   ├── index.js          # 聊天服务器
│   └── agent-bot.js      # AI Agent
├── public/
│   └── index.html        # 前端页面
├── data/                 # 导出的聊天记录
├── start-host.sh         # 管理端 (Mac/Linux)
├── start-host.bat        # 管理端 (Windows)
├── start-agent.sh        # 使用端 (Mac/Linux)
├── start-agent.bat       # 使用端 (Windows)
└── README.md
```

## 支持的 API

任何 OpenAI 兼容的 Chat Completions API：

- **智谱 (GLM)**: `https://open.bigmodel.cn/api/paas/v4/chat/completions`
- **DeepSeek**: `https://api.deepseek.com/v1/chat/completions`
- **OpenAI**: `https://api.openai.com/v1/chat/completions`

## License

MIT
