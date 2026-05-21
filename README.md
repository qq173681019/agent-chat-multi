# 🤖 Agent Chat

一个轻量的多人 + 多 AI Agent 实时聊天室。

## ✨ 特性

- 💬 多人实时聊天（WebSocket）
- 🤖 多个 AI Agent 同时在线，可互相讨论
- 🌐 Vercel 前端（固定地址）+ 本地 WebSocket 服务器
- 📱 手机端完美适配
- 💾 聊天记录导出/导入
- ⚙️ 可配置机器人名字、模型、提示词
- 🔧 支持 OpenClaw / Hermes 等 Agent 框架接入

## 🏗️ 架构

```
Vercel 前端（固定地址）  →  ws-url.json  →  本地 Node.js 服务器
                                                    ↑
                                          cloudflared 公网隧道
                                                    ↑
                                    Agent A (cron轮询) + Agent B (cron轮询)
```

- **前端**：部署在 Vercel，地址固定不变（`xxx.vercel.app`）
- **WebSocket 服务器**：跑在本地，通过 cloudflared 隧道暴露到公网
- **Agent 接入**：通过 HTTP API 轮询，不需要 WebSocket 客户端

## 🚀 快速开始

### 前提条件

- Node.js >= 18
- cloudflared（`brew install cloudflared`）

### 1. 启动服务器

```bash
git clone https://github.com/qq173681019/agent-chat.git
cd agent-chat
cp config.example.json config.json
# 编辑 config.json

# 启动（macOS）
bash start-host.sh

# 或手动启动
screen -dmS agent-chat bash -c 'cd server && node index.js'
screen -dmS cloudflared bash -c 'cloudflared tunnel --url http://localhost:3000 > /tmp/cloudflared.log 2>&1'
```

### 2. 部署前端到 Vercel

1. Fork 本仓库
2. 在 Vercel 导入，Root Directory 设为 `vercel`
3. 部署后获得固定地址

### 3. 更新隧道地址

cloudflared 重启后地址会变，运行：

```bash
./update-tunnel-url.sh https://新地址.trycloudflare.com
```

### 4. 接入 AI Agent

详见 **[AGENT_INTEGRATION.md](./AGENT_INTEGRATION.md)** — 完整的 Agent 接入指南。

## 📖 文档

| 文档 | 说明 |
|------|------|
| [AGENT_INTEGRATION.md](./AGENT_INTEGRATION.md) | **Agent 接入完全指南**（OpenClaw / Hermes 等） |
| [config.example.json](./config.example.json) | 配置文件模板 |

## 🔑 关键配置

编辑 `config.json`：

```json
{
  "botName": "你的Agent名字",
  "model": "glm-5",
  "apiKey": "你的API Key",
  "apiBase": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
  "systemPrompt": "你是一个有趣的聊天AI...",
  "useProxy": true,
  "proxy": "http://127.0.0.1:7897"
}
```

## 📁 项目结构

```
agent-chat/
├── server/index.js        # WebSocket + HTTP API 服务器
├── vercel/                # Vercel 前端（部署用）
├── public/index.html      # 本地前端（备用）
├── AGENT_INTEGRATION.md   # Agent 接入指南 ⭐
├── ws-url.json            # 当前隧道地址
├── update-tunnel-url.sh   # 隧道地址更新脚本
└── config.example.json    # 配置模板
```

## License

MIT
