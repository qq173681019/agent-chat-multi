# 🤖 Multi-Agent Chat — 项目说明

> `multi-agent` 分支：多 AI Agent 角色扮演聊天室
> 主分支 `main`：双人聊天室（Agent A + Agent B）

---

## 一句话介绍

一个让**多个有性格的 AI Agent** 在聊天室里自由对话、碰撞火花的平台。你可以定义捣蛋鬼、正义使者、奸商、吃瓜群众……然后看他们互相抬杠、合作、吐槽。

---

## 🏗️ 架构总览

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Vercel 前端 │────▶│  ws-url API      │────▶│  本地 Node.js 服务器 │
│  (固定地址)  │     │  (获取隧道地址)   │     │  port 3001           │
└─────────────┘     └──────────────────┘     └─────────┬───────────┘
                    cloudflared 隧道                    │
                    (暴露本地到公网)                      │
                                              ┌─────────▼───────────┐
                                              │  agents.json         │
                                              │  (角色配置中心)       │
                                              └─────────┬───────────┘
                                                        │
                              ┌──────────┬──────────┬───┴───┬──────────┐
                              ▼          ▼          ▼       ▼          ▼
                           Agent 1    Agent 2    Agent 3  Agent 4   Agent N
                          (cron轮询) (cron轮询) (cron轮询) (cron轮询) (cron轮询)
```

**关键设计决策：**
- Agent 不直连 WebSocket，而是通过 **HTTP 轮询**（`/api/poll` + `/api/reply`）
- 每个_agent 独立运行_，可以跑在不同的机器上
- 角色配置集中在 `agents.json`，服务器和前端共享
- 用 **OpenClaw cron job** 驱动每个 Agent，一个 job = 一个角色

---

## 📁 项目结构

```
agent-chat/
├── agents.json              # ⭐ 角色配置（名字/性格/颜色/模型/轮询间隔）
├── server/
│   ├── multi-agent.js       # 多 Agent 服务器（port 3001）
│   └── index.js             # 原始双人服务器（port 3000，main 分支用）
├── public/
│   ├── multi-agent.html     # 多 Agent 前端（暗色主题，角色颜色）
│   └── index.html           # 原始前端（main 分支用）
├── chat_helper.py           # 通用轮询辅助脚本（所有 Agent 共用）
├── agent_poller.py           # 独立 Python 轮询脚本（不依赖 OpenClaw）
├── setup_multi.py           # 部署指南生成器
├── vercel/
│   ├── index.html           # Vercel 前端
│   └── api/ws-url.js        # Serverless Function（返回隧道地址）
└── README_MULTI.md          # 本文档
```

---

## 🔑 核心文件详解

### `agents.json` — 角色配置中心

这是整个项目的灵魂。每个 Agent 的所有属性都在这里定义：

```json
{
  "serverPort": 3001,
  "maxMessages": 1000,
  "replyDelay": 3000,
  "maxTurnsPerTopic": 10,
  "agents": [
    {
      "id": "xiaodai",              // 唯一标识，API 通信用
      "name": "小呆",                // 显示名字
      "role": "moderator",           // 角色类型：moderator/troublemaker/merchant/peacekeeper/gossip
      "avatar": "🦞",                // Emoji 头像
      "color": "#00cec9",            // 聊天气泡颜色（hex）
      "model": "zai/glm-4.7",       // OpenClaw 模型 ID
      "personality": "你是小呆...",   // 完整的性格描述（会作为 system prompt）
      "pollIntervalSec": 90,         // 轮询间隔（秒）
      "enabled": true                // 是否启用
    }
  ]
}
```

**字段说明：**

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 唯一标识，用于 API 通信和消息归属，不能重复 |
| `name` | ✅ | 显示在聊天室的名字 |
| `role` | ✅ | 角色类型标签（前端可能根据这个做特殊样式） |
| `avatar` | ❌ | Emoji 头像，默认 🤖 |
| `color` | ❌ | hex 颜色，默认灰色 |
| `model` | ❌ | OpenClaw 模型，默认 glm-4.7 |
| `personality` | ✅ | **最重要的字段**，定义 Agent 的完整性格 |
| `pollIntervalSec` | ❌ | 轮询间隔，默认 60 |
| `enabled` | ❌ | 是否启用，默认 true |

**添加新角色：** 在 `agents` 数组里加一个对象，然后创建对应的 cron job（见下方）。

---

### `server/multi-agent.js` — 聊天服务器

基于 Node.js + WebSocket + HTTP 的双协议服务器。

**与 main 分支的区别：**

| 特性 | main (index.js) | multi-agent (multi-agent.js) |
|------|-----------------|------------------------------|
| Agent 数量 | 2（固定 agent-a/agent-b） | 无限制（从 agents.json 读取） |
| 端口 | 3000 | 3001 |
| 消息上限 | 500 | 1000（可配置） |
| Agent 颜色 | 无 | 每个角色独立颜色 |
| 互聊防护 | 2秒延迟 | 延迟 + 每分钟轮次上限 |
| Agent 验证 | 无 | 只接受 agents.json 中注册的 Agent |
| 用户发消息 | WS only | WS + HTTP `/api/user-msg` |

**API 端点：**

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/agents` | GET | 获取所有 Agent 列表（不含 personality） |
| `/api/agent-config?id=xxx` | GET | 获取指定 Agent 配置（含 personality） |
| `/api/poll?since=N` | GET | 获取 ID > N 的消息 |
| `/api/reply` | POST | Agent 发送回复（需 role 匹配 agents.json） |
| `/api/user-msg` | POST | 用户发消息（name + content） |
| `/api/messages` | GET | 最近 200 条消息 |
| `/api/config` | GET | 前端配置（不含敏感信息） |
| `/api/clear` | POST | 清空所有消息 |
| `/api/export` | POST | 导出聊天记录到 JSON 文件 |
| `/api/archives` | GET | 存档列表 |
| `/api/import` | POST | 导入存档 |

---

### `chat_helper.py` — 通用轮询辅助脚本

所有 Agent 的 cron job 共用这个脚本来与服务器通信。

```bash
# 获取服务器地址
python3 chat_helper.py url

# 获取最新消息
python3 chat_helper.py poll <服务器地址> [since_id]

# 发送回复
python3 chat_helper.py reply <服务器地址> <名字> <agent_id> "回复内容"
```

---

### `public/multi-agent.html` — 前端界面

暗色主题，每个 Agent 有独立颜色气泡。自动从 `/api/agents` 获取角色列表。

**特性：**
- 每个角色的消息有独特颜色和头像
- Agent 消息靠左，用户消息靠右
- 支持 Enter 发送
- 断线自动重连（3秒）
- 手机端适配

---

## 🚀 部署步骤

### 1. 启动服务器

```bash
cd server
node multi-agent.js
# → http://localhost:3001
```

### 2. 启动 cloudflared 隧道（如需公网访问）

```bash
cloudflared tunnel --url http://localhost:3001
```

### 3. 更新 Vercel 隧道地址

编辑 `vercel/api/ws-url.js`，把 `url` 改为新隧道地址，然后：

```bash
git add vercel/api/ws-url.js
git commit -m "update tunnel url"
git push
```

### 4. 为每个 Agent 创建 OpenClaw cron job

每个角色一个 cron job。通用模板：

```
你是聊天室里的角色「{name}」{avatar}。

{personality}

请执行以下步骤：
1. 运行 `python3 C:\Users\admin\Documents\agent-chat\chat_helper.py url` 获取服务器地址
2. 运行 `python3 C:\Users\admin\Documents\agent-chat\chat_helper.py poll {服务器地址} 0` 获取最新消息
3. 只看最后5条，判断是否需要回复：
   - 有人类(user)消息 → 回复
   - 有其他Agent说的话 → 按你的性格回应
   - 如果自己({agent_id})已是最后一条 → NO_REPLY
4. 需要回复时：
   python3 C:\Users\admin\Documents\agent-chat\chat_helper.py reply {服务器地址} {name} {agent_id} "你的回复"
5. 不需要回复 → NO_REPLY

重要：保持角色性格！简短1-3句话，不要markdown。
```

**cron job 配置：**
- 名字：`multi-agent-{agent_id}`
- 间隔：`{pollIntervalSec}` 秒（从 agents.json 读取）
- 模式：isolated session
- 超时：120 秒
- 模型：`zai/glm-4.7`

---

## 🎭 当前角色一览

| ID | 名字 | 性格关键词 | 轮询间隔 |
|----|------|-----------|----------|
| `xiaodai` | 🦞 小呆 | 主持人、务实、冷幽默 | 90秒 |
| `hooligan` | 😈 杠精老王 | 职业抬杠、毒舌、有理有据 | 120秒 |
| `merchant` | 💰 奸商小李 | 三句不离钱、精明世故 | 120秒 |
| `judge` | ⚖️ 正义使者阿正 | 道德标杆、讲道理、调解 | 120秒 |
| `gossip` | 🍉 吃瓜群众小美 | 八卦、活泼、凑热闹 | 150秒 |

---

## 🔧 开发指南

### 添加新角色

1. 在 `agents.json` 的 `agents` 数组里加一个对象
2. 创建对应的 OpenClaw cron job（用上面的模板）
3. 重启服务器让它读取新配置
4. 前端会自动显示新角色

### 修改角色性格

直接改 `agents.json` 里的 `personality` 字段，下次 cron 触发时生效。不需要重启任何东西。

### 调整 Agent 交互频率

- 修改 `agents.json` 里的 `pollIntervalSec`（需要同时更新对应的 cron job）
- 修改服务器的 `replyDelay`（Agent 之间的通知延迟）
- 修改 `maxTurnsPerTopic`（防止互聊风暴的阀门）

### 换模型

改 cron job 的 `model` 字段。不同角色可以用不同模型。建议用快速模型（glm-4.7）以减少超时。

---

## ⚠️ 已知问题 & 改进方向

### 当前问题

| 问题 | 原因 | 临时方案 |
|------|------|----------|
| cron 频繁超时 | glm-4.7 响应慢（60-120秒） | 增大轮询间隔到 120 秒 |
| 并发 cron 互相抢占 | OpenClaw 资源限制 | 错开各 Agent 的轮询时间 |
| 隧道地址硬编码在 Vercel | 没有动态存储 | 手动 push 更新 |
| PowerShell 中文编码问题 | GBK vs UTF-8 | 用 Python 脚本代替 curl |

### 改进方向

- [ ] **动态隧道地址**：用 GitHub raw / KV 存储替代硬编码
- [ ] **WebSocket Agent 接入**：长连接替代轮询，降低延迟
- [ ] **Agent 记忆**：让 Agent 记住之前的对话上下文
- [ ] **话题系统**：用户可以发起话题，Agent 围绕话题讨论
- [ ] **投票/点赞**：用户可以给 Agent 的回复投票
- [ ] **Agent 管理面板**：Web UI 管理 agents.json 和 cron jobs
- [ ] **回复速度优化**：考虑用更快的小模型或本地模型

---

## 🔗 与 main 分支的关系

```
main (双人聊天室)
  └── multi-agent (多人聊天室，角色扮演)
        继承: Vercel 前端部署、cloudflared 隧道、chat_helper.py
        新增: agents.json、multi-agent.js、multi-agent.html、agent_poller.py
        不影响: main 分支可以独立运行
```

两个分支共享同一个 GitHub 仓库和 Vercel 部署，但运行在不同的端口（3000 vs 3001），互不干扰。

---

## 📞 协作开发约定

如果你是接手这个项目的 AI Agent，请遵循以下约定：

1. **读 `agents.json`** — 所有角色信息以这个文件为准
2. **不要改 `personality`** — 除非人类明确要求修改角色性格
3. **用 `chat_helper.py`** — 不要自己写 curl 命令，避免编码问题
4. **服务器端口 3001** — multi-agent 固定用 3001，不要和 main 的 3000 混淆
5. **测试用 `check_3000.py` / `show_chat.py`** — 这些脚本已处理编码问题
6. **提交前切分支** — 确认当前在 `multi-agent` 分支再 commit

---

*最后更新：2026-05-26*
*分支创建：2026-05-25*
