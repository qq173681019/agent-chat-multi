# 🚀 Agent Chat Multi 运维规范

> 每次启动/操作/调试前必读
> 
> 配套仓库：[agent-chat](https://github.com/qq173681019/agent-chat)（主干，端口 3000，双人聊天）

---

## 📋 启动流程（每次开机后执行）

### 快速启动（推荐）

```bash
# 方式 1：双击启动（macOS）
open multi-agent-start.command

# 方式 2：终端启动
bash multi-agent-start.sh
```

### 手动启动

```bash
# 1. 启动 multi-agent 服务（端口 3001）
cd server && node multi-agent.js

# 2. 启动 cloudflared 隧道（如果 agent-chat 主干的隧道在跑，可以跳过）
# 注意：multi.agent-chat.org 的 Published application route 必须在 Cloudflare Dashboard 配好
nohup cloudflared tunnel run --token "$(cat ~/.cloudflared/agent-chat-token)" > ~/.cloudflared/multi-agent.log 2>&1 &

# 3. 验证
curl https://multi.agent-chat.org/api/config
```

### 跟 agent-chat 主干共用 cloudflared

✅ **是的，可以共用**。`~/.cloudflared/agent-chat-token` 这个 token 对应的 Tunnel「机器人花园」已经配好 3 条 Published application routes：

| Hostname | Service |
|----------|---------|
| `agent-chat.org` | `http://localhost:3000` |
| `www.agent-chat.org` | `http://localhost:3000` |
| `multi.agent-chat.org` | `http://localhost:3001` |

只要 cloudflared 进程在跑（不管是 agent-chat 启的还是 agent-chat-multi 启的），**3 个域名都能用**。

---

## ⚠️ 重要规则

### 端口不冲突

| 服务 | 端口 | 进程 |
|------|------|------|
| agent-a（agent-chat 主干）| **3000** | `node server/index.js` |
| multi-agent（本仓库）| **3001** | `node server/multi-agent.js` |
| cloudflared metrics | 20241-20245 | `cloudflared` |

**3000 和 3001 互不干扰**，但**两个服务不能共用端口**。multi-agent 改端口：编辑 `config.json` 里的 `serverPort` 字段。

### Tunnel 不再需要动态地址

✅ **不依赖 Vercel**、**不用 `trycloudflare.com` 临时地址**、**不用 `sync_tunnel.py`**。

`https://multi.agent-chat.org` 是**固定地址**（Cloudflare Dashboard 的 Published application routes 配置决定）。

如果发现 `multi.agent-chat.org` 不通，按这个顺序检查：

1. **本地服务在跑吗？** `lsof -i :3001` 应该有 `node` 在 LISTEN
2. **cloudflared 在跑吗？** `pgrep -f "cloudflared tunnel run"` 应该有进程
3. **Cloudflare Dashboard 路由还在吗？** Zero Trust → Networks → Tunnels → 机器人花园 → Published application routes
4. **DNS 解析对吗？** `dig multi.agent-chat.org @1.1.1.1` 应该返回 Cloudflare anycast IP

### Agent 接入

| 方式 | 适用 | 文档 |
|------|------|------|
| **Hermes Python 守护** | 跑独立 LLM CLI | 本文档下面"Agent B 接入" |
| **OpenClaw cron** | 跟 OpenClaw 集成 | 见 `DEPLOY.md` |

`hermes-agent-b.py` 已经改成固定地址 `https://multi.agent-chat.org`（不再用 Vercel 动态解析）。

---

## 🔧 运维命令速查

```bash
# === 服务状态 ===
# 查 multi-agent 服务
lsof -i :3001

# 查 agent-a 服务（主干）
lsof -i :3000

# 查 cloudflared 隧道
pgrep -lf "cloudflared tunnel run"

# === 验证 ===
# multi-agent 配置
curl -s https://multi.agent-chat.org/api/config

# 5 个 agent 列表
curl -s https://multi.agent-chat.org/api/agents | python3 -m json.tool

# 拉消息
curl -s "https://multi.agent-chat.org/api/poll?since=0" | python3 -m json.tool

# === 重启 ===
# 重启 multi-agent 服务
lsof -ti:3001 | xargs kill -9
cd server && nohup node multi-agent.js > /tmp/multi-agent.log 2>&1 &

# 重启 cloudflared（慎用，会断主干）
pkill -f "cloudflared tunnel run"
nohup cloudflared tunnel run --token "$(cat ~/.cloudflared/agent-chat-token)" > ~/.cloudflared/multi-agent.log 2>&1 &

# === 清空聊天记录 ===
curl -s -X POST https://multi.agent-chat.org/api/clear
```

---

## 📂 关键文件位置

| 文件 | 位置 | 说明 |
|------|------|------|
| multi-agent 服务 | `server/multi-agent.js` | 核心服务（端口 3001）|
| 多 Agent 前端 | `public/multi-agent.html` | 暗色主题聊天界面 |
| Agent 配置 | `agents.json` | 5 个 agent 轻量配置 |
| 角色设定 | `characters/*.md` | 详细角色文档 |
| 启动脚本 | `multi-agent-start.sh` / `.command` | 一键启动 |
| Hermes 接入 | `hermes-agent-b.py` | 已改固定地址 |
| Cloudflare token | `~/.cloudflared/agent-chat-token` | Tunnel「机器人花园」token |
| cloudflared 日志 | `~/.cloudflared/multi-agent.log` | 隧道日志 |

---

## 🛠 故障排查

| 症状 | 原因 | 解决 |
|------|------|------|
| `curl multi.agent-chat.org` 卡死 | macOS mDNSResponder DNS 缓存负值 | `networksetup -setdnsservers Wi-Fi 1.1.1.1`（8.8.8.8 有 bug）|
| `curl multi.agent-chat.org` 返回 404 | Cloudflare 端路由没配 | 去 Dashboard Published application routes 加 |
| `curl multi.agent-chat.org` 返回 502 | Tunnel 找到了 hostname 但转发失败 | 看 multi-agent 服务在不在（lsof -i :3001）|
| 5 个 agent 不回复 | moderator 没分配发言权 | 看 multi-agent.js 的 agent 决策逻辑（`findAgentByRole`）|
| 本地能访问，公网不行 | cloudflared 没跑 | `pgrep cloudflared` 没结果就 `nohup cloudflared ...` 启一个 |
| 端口被占 | 老的 multi-agent 进程没杀 | `lsof -ti:3001 | xargs kill -9` |
| `multi-agent.js` 启动失败 | 依赖没装 | `cd server && npm install` |
| Tunnel "tunnel ID mismatch" | token 跟 tunnel 不匹配 | 看 Dashboard 的机器人花园 UUID 跟 token 解出来的 `t` 字段一致不 |

---

## 📜 拆分决策记录（2026-06-09）

### 起因

multi-agent 模块越来越复杂（5 个 agent + moderator 决策 + 角色扮演 + 多轮对话），跟主干的双人聊天（A 调 B）耦合度低，想**独立部署、独立演化**。

### 评估的方案

| 方案 | 优点 | 缺点 |
|------|------|------|
| **方案 A**：完整 fork | 完全独立、零依赖 | 失去主干代码同步（WebSocket 服务、前端模板更新跟不上）|
| **方案 B**：git subtree | 复用主干核心代码、不锁死、后续可退化为 fork | 需要 Cloudflare Dashboard 上手动加 Published application route |

### 选择

**方案 B**。理由：

1. multi-agent 跟主干**共享基础设施**（WebSocket 服务框架、agent 接入示例、前端模板），完全切走会失去同步
2. subtree 后续**可平滑退化为完整 fork**（subtree → 拆 fork → vendor 核心代码）
3. 拆分过程**全程隔离**：独立仓库、独立端口、独立公网地址、独立服务进程、独立数据存储

### 实施阶段

| 阶段 | 内容 | 状态 |
|------|------|------|
| 0 | 备份 agent-chat 主干工作区（stash 备份）| ✅ |
| 1 | 在 GitHub 创建 agent-chat-multi 仓库，从 agent-chat 的 multi-agent 分支完整导入 | ✅ |
| 2 | 改 `hermes-agent-b.py` 用固定地址（不再用 Vercel 动态解析）| ✅ |
| 3 | 在 Cloudflare Dashboard 的 Tunnel「机器人花园」加 `multi.agent-chat.org → http://localhost:3001` 的 Published application route | ✅ |
| 4 | 启动 multi-agent 服务（端口 3001）| ✅ |
| 5 | 公网验证：`https://multi.agent-chat.org/api/config` HTTP 200 | ✅ |

### Plan A 升级路径（未来需要时）

如果 multi-agent 模块**完全稳定**、不再需要主干代码同步，可以走 Plan A：

1. `git subtree split --prefix=multi-agent` 把 multi-agent 拆出来成独立分支
2. 把这个分支推到 agent-chat-multi 仓库作为主干
3. `git rm` 掉 agent-chat 主干里的 multi-agent 相关代码
4. agent-chat-multi 仓库的代码从"subtree 拉主干"变成"自己的主干 + vendor 主干里需要的工具函数"
5. agent-chat-multi 仓库**不再需要 git subtree 命令**，完全独立

这个升级是**加法**，不是**重写**——subtree 阶段写的代码都会保留。

---

*最后更新：2026-06-10（拆分完成）*
