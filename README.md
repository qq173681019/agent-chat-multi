# 🤖 Agent Chat

一个轻量的 AI 聊天室，支持多人和 AI Agent 实时对话。

## 功能

- 💬 多人实时聊天（WebSocket）
- 🤖 AI Agent 自动回复（接入 GLM / DeepSeek / OpenAI 等）
- 💾 聊天记录导出/导入
- 📱 手机端适配
- ⚙️ 可配置机器人名字、模型、提示词

## 快速开始

### 1. 安装依赖

```bash
cd server
npm install
```

### 2. 配置

编辑 `config.json`：

```json
{
  "botName": "你的机器人名字",
  "apiKey": "你的API Key",
  "apiBase": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
  "model": "glm-4-flash",
  "useProxy": false,
  "proxy": "http://127.0.0.1:7897"
}
```

### 3. 启动

**macOS / Linux：**
```bash
bash start.sh
```

**Windows：**
```cmd
start.bat
```

### 4. 访问

- 本地：http://localhost:3000
- 如果需要公网访问，脚本会自动启动 ngrok 隧道

## 配置说明

| 字段 | 说明 | 默认值 |
|------|------|--------|
| botName | 机器人在聊天室显示的名字 | 顾小狼的小胡子 |
| botRole | Agent 角色 (agent-a / agent-b) | agent-a |
| apiKey | LLM API Key | 必填 |
| apiBase | API 地址 | 智谱 API |
| model | 使用的模型 | glm-4-flash |
| useProxy | 是否使用代理 | true |
| proxy | 代理地址 | http://127.0.0.1:7897 |
| systemPrompt | 系统提示词（{botName} 会被替换） | 见配置文件 |
| serverPort | 服务端口 | 3000 |

## 项目结构

```
agent-chat/
├── config.json          # 配置文件（机器人名字、API Key等）
├── server/
│   ├── index.js         # 主服务（HTTP + WebSocket）
│   └── agent-bot.js     # AI Agent Bot
├── public/
│   └── index.html       # 前端页面
├── data/                # 导出的聊天记录（自动创建）
├── start.sh             # macOS/Linux 启动脚本
├── start.bat            # Windows 启动脚本
└── README.md
```

## 支持的 API

任何 OpenAI 兼容的 Chat Completions API：

- **智谱 (GLM)**: `https://open.bigmodel.cn/api/paas/v4/chat/completions`
- **DeepSeek**: `https://api.deepseek.com/v1/chat/completions`
- **OpenAI**: `https://api.openai.com/v1/chat/completions`

## License

MIT
