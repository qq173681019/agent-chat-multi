# 🚀 Agent Chat Multi 部署指南

> 本文档面向 **AI Agent** 或人类操作者。
> 目标：在一台新电脑上启动多 Agent 聊天室服务。
> 
> 配套仓库：[agent-chat](https://github.com/qq173681019/agent-chat)（主干，端口 3000，双人聊天）

---

## 一、搞清楚：你要跑什么？

这个项目**只跑多 Agent 模式**。如果你要跑原始的双人聊天（A 调 B），请去 [agent-chat 仓库](https://github.com/qq173681019/agent-chat)。

| 角色 | 干什么 | 跑在哪 |
|------|--------|--------|
| **服务器** | 5 个 Agent 聊天室核心，转发消息、moderator 决策 | 任何一台能开机的电脑 |
| **人类用户** | 浏览器/curl 发消息，看 5 个 agent 讨论 | 任何能联网的设备 |

**最简配置：一台电脑跑服务器 + 5 个内置 agent，浏览器打开 `https://multi.agent-chat.org` 就能玩。**

> **注意**：multi-agent 服务**只接受 5 个内置 agent**（xiaodai / hooligan / merchant / judge / gossip）。
> 外部 agent-b / 第三方接入**当前不支持**（`/api/reply` 只校验内置 agent ID）。
> 人类用户（user）可以直接通过浏览器发消息参与讨论。

---

## 二、跑服务器（5 Agent 聊天室核心）

### 前提

- Node.js >= 18
- cloudflared（`brew install cloudflared`）
- Cloudflare 账号 + Tunnel「机器人花园」里**已经配好** `multi.agent-chat.org` 的 Published application route

### 一键启动

```bash
git clone https://github.com/qq173681019/agent-chat-multi.git
cd agent-chat-multi
cp config.example.json config.json
# 编辑 config.json，填入：
#   serverPort: 3001（默认）
#   apiKey: 你的 LLM API Key（multi-agent 用 moderator 决策时会调 LLM）
#   apiBase / model / proxy：看你用哪个 LLM
#   agentBots[]：5 个内置 agent 的配置

# macOS / Linux
bash multi-agent-start.sh

# macOS Finder 双击
open multi-agent-start.command
```

启动后会显示：
- 本地地址：`http://localhost:3001`
- 公网地址：`https://multi.agent-chat.org`（**永远是这个地址**）

### 手动启动

```bash
cd agent-chat-multi
(cd server && npm install)  # 首次

# 启动 multi-agent 服务
cd server && nohup node multi-agent.js > /tmp/multi-agent.log 2>&1 &

# 启动 cloudflared 隧道（如果主干 agent-chat 的隧道在跑，可以跳过）
nohup cloudflared tunnel run --token "$(cat ~/.cloudflared/agent-chat-token)" > ~/.cloudflared/multi-agent.log 2>&1 &

# 验证
curl -s https://multi.agent-chat.org/api/config
```

### 配置说明

`config.json`（从 `config.example.json` 复制）：

```json
{
  "serverPort": 3001,
  "apiKey": "你的API Key",
  "apiBase": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
  "model": "glm-5",
  "moderatorModel": "glm-5",
  "useProxy": true,
  "proxy": "http://127.0.0.1:7897",
  "agents": [
    { "id": "xiaodai",  "name": "小呆",       "role": "moderator" },
    { "id": "hooligan", "name": "杠精老王",   "role": "troublemaker" },
    { "id": "merchant", "name": "奸商小李",   "role": "merchant" },
    { "id": "judge",    "name": "正义使者阿正", "role": "peacekeeper" },
    { "id": "gossip",   "name": "吃瓜群众小美", "role": "gossip" }
  ]
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `serverPort` | 可选 | 默认 3001 |
| `apiKey` | ✅ | moderator 决策用 |
| `apiBase` | ✅ | LLM API 地址 |
| `model` | ✅ | 主用模型 |
| `moderatorModel` | 可选 | moderator 专用模型（默认同 model）|
| `useProxy` | 按需 | 国内访问海外 API 需要 |
| `proxy` | 按需 | 代理地址 |
| `agents` | ✅ | 5 个内置 agent 配置 |

---

## 三、整体架构图

```
    📱 手机/电脑浏览器 (5 个内置 agent 的暗色 UI)
         │
         ▼
   https://multi.agent-chat.org  (固定公网地址)
         │
         │  Cloudflare Tunnel「机器人花园」
         │  Published application route: multi.agent-chat.org → :3001
         ▼
   本地 Node.js multi-agent 服务 (端口 3001)
         │
         ├─ 5 个内置 Agent (agents.json + characters/*.md)
         │   └─ moderator 决策谁该回复
         │
         └─ 人类用户 (浏览器/curl) → 5 个 agent 都可能回复
```

---

## 四、跟主干 agent-chat 的关系

| 维度 | agent-chat（主干）| agent-chat-multi（本仓）|
|------|-------------------|------------------------|
| 仓库 | `qq173681019/agent-chat` | `qq173681019/agent-chat-multi` |
| 端口 | 3000 | 3001 |
| 公网地址 | `agent-chat.org` | `multi.agent-chat.org` |
| Agent 数 | 1 | 5 |
| 模式 | 双人聊天（A 调 B）| 多人角色扮演 |
| 启动脚本 | `start-host.sh` / `agent-chat-start.command` | `multi-agent-start.sh` / `multi-agent-start.command` |
| 配置文件 | `config.json` | `config.json`（在各自仓库）|
| Cloudflare token | `~/.cloudflared/agent-chat-token` | **同一个**（共用 Tunnel）|
| 依赖 | Node.js + cloudflared | Node.js + cloudflared |
| 是否可以同机跑 | ✅ 是 | ✅ 是 |

**两者共享 Cloudflare Tunnel**（都用「机器人花园」这个 tunnel），但**进程独立、端口独立、数据独立**。

---

## 五、常见问题

| 问题 | 解决 |
|------|------|
| `multi.agent-chat.org` 不通 | 见 `OPERATIONS.md` 故障排查 |
| 5 个 agent 不回复 | moderator 决策可能没识别 user 消息，看 `multi-agent.js` 的 `findAgentByRole` |
| Cloudflare Dashboard 找不到 Published application routes tab | 在 Tunnel「机器人花园」详情页找（在 CIDR routes 和 Hostname routes 之间的那个 tab）|
| 端口 3001 被占 | `lsof -ti:3001 | xargs kill -9` |
| 想要第 6 个 agent | **当前不支持**。需要改 multi-agent.js 放开 agent 校验逻辑，再加到 agents.json |
| 想换 LLM 模型 | 改 `config.json` 的 `model` 和 `moderatorModel` 字段 |
| 想换端口 | 改 `config.json` 的 `serverPort` 字段 + Cloudflare Dashboard 的 Published application route URL |
| macOS DNS 缓存负值导致 curl 卡死 | `networksetup -setdnsservers Wi-Fi 1.1.1.1`（8.8.8.8 有 bug）|

---

## 六、快速迁移检查清单

把 multi-agent 服务迁移到新电脑时，逐项确认：

- [ ] `git clone https://github.com/qq173681019/agent-chat-multi.git`
- [ ] 安装 Node.js 18+ 和 cloudflared
- [ ] 创建 `config.json`（从 `config.example.json` 复制）
- [ ] 填入 API Key、模型、proxy 等
- [ ] 复制 `~/.cloudflared/agent-chat-token`（如果新电脑还没配）
- [ ] 跑 `bash multi-agent-start.sh`
- [ ] 验证 `curl https://multi.agent-chat.org/api/config` 返回 200
- [ ] 浏览器打开 `https://multi.agent-chat.org` 测试聊天

---

*最后更新：2026-06-10（拆分完成）*
