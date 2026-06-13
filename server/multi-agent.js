const http = require('http');
const fs = require('fs');
const path = require('path');
const WebSocket = require('ws');

// ============ 配置 ============
const CONFIG_PATH = path.join(__dirname, '../agents.json');
const DATA_DIR = path.join(__dirname, '../data');

let config;
try {
  config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8'));
} catch (e) {
  console.error('❌ 无法读取 agents.json:', e.message);
  process.exit(1);
}

const PORT = config.serverPort || 3001;
const MAX_MESSAGES = config.maxMessages || 1000;
const REPLY_DELAY = config.replyDelay || 3000;
const MAX_TURNS = config.maxTurnsPerTopic || 10;

if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

// ============ 数据 ============
const messages = [];
let msgId = 0;
const users = {};
let userIdCounter = 0;

// Agent 在线状态 & 对话追踪
const agentState = {};
config.agents.forEach(a => {
  agentState[a.id] = { online: false, ws: null, lastSeen: 0, conversationTurns: 0 };
});

// Typing indicators
const typingState = {}; // agentId -> { started: timestamp, timeout: timer }

// Reactions: msgId -> [{ userId, emoji }]
const reactions = {};

// Agent short-term memory: agentId -> [last N messages they saw]
const agentMemory = {};
config.agents.forEach(a => {
  agentMemory[a.id] = [];
});

// ============ 工具函数 ============
function getAgents() {
  return config.agents.filter(a => a.enabled !== false);
}

function findAgentByRole(role) {
  return getAgents().find(a => a.id === role);
}

function findAgentByName(name) {
  return getAgents().find(a => a.name === name);
}

function countRecentTurns(sinceMs = 60000) {
  const cutoff = Date.now() - sinceMs;
  return messages.filter(m => m.time > cutoff && m.role !== 'user' && m.role !== 'system').length;
}

function shouldAgentReply(agentId) {
  if (countRecentTurns(60000) >= MAX_TURNS) return false;
  const last3 = messages.slice(-3);
  const selfRecent = last3.filter(m => m.role === agentId).length;
  return selfRecent < 2;
}

function broadcast(data) {
  const raw = JSON.stringify(data);
  wss.clients.forEach(client => {
    if (client.readyState === WebSocket.OPEN) client.send(raw);
  });
}

function updateAgentMemory(agentId, msg) {
  if (!agentMemory[agentId]) agentMemory[agentId] = [];
  agentMemory[agentId].push(msg);
  // Keep last 20 messages
  if (agentMemory[agentId].length > 20) agentMemory[agentId].shift();
}

// ============ HTTP ============
const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  const url = new URL(req.url, `http://${req.headers.host}`);

  // 首页
  if (url.pathname === '/' || url.pathname === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(fs.readFileSync(path.join(__dirname, '../public/multi-agent.html')));
    return;
  }

  // Health check
  if (url.pathname === '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      status: 'ok',
      uptime: process.uptime(),
      messageCount: messages.length,
      agents: getAgents().map(a => ({
        id: a.id,
        name: a.name,
        online: agentState[a.id]?.online || false
      })),
      users: Object.keys(users).length,
      timestamp: Date.now()
    }));
    return;
  }

  // 获取 agent 列表
  if (url.pathname === '/api/agents') {
    const agents = getAgents().map(a => ({
      id: a.id, name: a.name, avatar: a.avatar, color: a.color, role: a.role,
      online: agentState[a.id]?.online || false,
      lastSeen: agentState[a.id]?.lastSeen || 0
    }));
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ agents }));
    return;
  }

  // 获取配置（前端用，不暴露 personality）
  if (url.pathname === '/api/config') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      serverPort: PORT,
      agentCount: getAgents().length,
      mode: 'multi-agent',
      agents: getAgents().map(a => ({ id: a.id, name: a.name, avatar: a.avatar, color: a.color }))
    }));
    return;
  }

  // 轮询消息
  if (url.pathname === '/api/poll' && req.method === 'GET') {
    const since = parseInt(url.searchParams.get('since') || '0');
    const pending = messages.filter(m => m.id > since && m.role !== 'system');
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ messages: pending, lastId: msgId }));
    return;
  }

  // 获取某个 agent 的配置（含 personality 和 memory）
  if (url.pathname === '/api/agent-config' && req.method === 'GET') {
    const agentId = url.searchParams.get('id');
    const agent = getAgents().find(a => a.id === agentId);
    if (!agent) {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Agent not found' }));
      return;
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      id: agent.id, name: agent.name, avatar: agent.avatar,
      personality: agent.personality, model: agent.model,
      pollIntervalSec: agent.pollIntervalSec,
      recentMemory: agentMemory[agent.id] || []
    }));
    return;
  }

  // 搜索消息
  if (url.pathname === '/api/search' && req.method === 'GET') {
    const query = (url.searchParams.get('q') || '').toLowerCase();
    const limit = Math.min(parseInt(url.searchParams.get('limit') || '20'), 50);
    if (!query) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Missing query parameter q' }));
      return;
    }
    const results = messages.filter(m =>
      m.content && m.content.toLowerCase().includes(query)
    ).slice(-limit);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ results, total: results.length }));
    return;
  }

  // Typing indicator
  if (url.pathname === '/api/typing' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        const agentId = data.agentId || data.role;
        const agent = findAgentByRole(agentId);
        if (!agent) {
          res.writeHead(403); res.end(JSON.stringify({ error: 'Unknown agent' }));
          return;
        }
        // Broadcast typing state
        broadcast({
          type: 'typing',
          agentId: agent.id,
          agentName: agent.name,
          avatar: agent.avatar,
          isTyping: data.isTyping !== false,
          time: Date.now()
        });
        // Auto-clear after 10s
        if (data.isTyping !== false) {
          if (typingState[agentId]) clearTimeout(typingState[agentId].timeout);
          typingState[agentId] = {
            started: Date.now(),
            timeout: setTimeout(() => {
              broadcast({ type: 'typing', agentId: agent.id, agentName: agent.name, avatar: agent.avatar, isTyping: false, time: Date.now() });
            }, 10000)
          };
        }
        res.writeHead(200); res.end(JSON.stringify({ ok: true }));
      } catch (e) {
        res.writeHead(400); res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  // Reactions
  if (url.pathname === '/api/react' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        const msgIdTarget = data.msgId;
        const emoji = data.emoji;
        const userId = data.userId || data.from || 'anonymous';

        if (!msgIdTarget || !emoji) {
          res.writeHead(400); res.end(JSON.stringify({ error: 'Missing msgId or emoji' }));
          return;
        }

        if (!reactions[msgIdTarget]) reactions[msgIdTarget] = [];

        // Toggle reaction
        const existing = reactions[msgIdTarget].findIndex(r => r.userId === userId && r.emoji === emoji);
        if (existing >= 0) {
          reactions[msgIdTarget].splice(existing, 1);
        } else {
          reactions[msgIdTarget].push({ userId, emoji, time: Date.now() });
        }

        broadcast({
          type: 'reaction',
          msgId: msgIdTarget,
          reactions: reactions[msgIdTarget],
          time: Date.now()
        });

        res.writeHead(200);
        res.end(JSON.stringify({ ok: true, reactions: reactions[msgIdTarget] }));
      } catch (e) {
        res.writeHead(400); res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  // 发送消息（agent 用）
  if (url.pathname === '/api/reply' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        const agentId = data.role || data.id;

        // 验证 agent 是否存在
        const agent = findAgentByRole(agentId) || findAgentByName(data.from);
        if (!agent) {
          res.writeHead(403, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Unknown agent' }));
          return;
        }

        // Update agent state
        agentState[agent.id].online = true;
        agentState[agent.id].lastSeen = Date.now();

        // Clear typing
        if (typingState[agent.id]) {
          clearTimeout(typingState[agent.id].timeout);
          delete typingState[agent.id];
          broadcast({ type: 'typing', agentId: agent.id, agentName: agent.name, avatar: agent.avatar, isTyping: false, time: Date.now() });
        }

        msgId++;
        // 2026-06-13 16:08: 修协议 — agent-bot.js 改发 HTTP POST, 加 fromPrefix 字段
        // 兜底模型回复时, fromPrefix='傻傻的' 拼在 from 字段前, 让其他 bot 能识别
        const msg = {
          id: msgId,
          from: (data.fromPrefix || '') + (agent.name || data.from),
          fromId: agent.id,
          role: agent.id,
          avatar: agent.avatar,
          content: data.content,
          time: Date.now()
        };
        messages.push(msg);
        if (messages.length > MAX_MESSAGES) messages.splice(0, messages.length - MAX_MESSAGES);

        // Update all agents' memory
        getAgents().forEach(a => updateAgentMemory(a.id, msg));

        broadcast({ type: 'message', ...msg });

        // 通知其他 agent（带延迟，防止互聊风暴）
        getAgents().forEach(other => {
          if (other.id === agent.id) return;
          const state = agentState[other.id];
          if (state?.ws && state.ws.readyState === WebSocket.OPEN) {
            setTimeout(() => {
              state.ws.send(JSON.stringify({ type: 'agent_query', message: msg }));
            }, REPLY_DELAY);
          }
        });

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, id: msgId }));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  // 用户发消息
  if (url.pathname === '/api/user-msg' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        msgId++;
        const msg = {
          id: msgId,
          from: data.name || '匿名用户',
          fromId: data.userId || 'user_' + (++userIdCounter),
          role: 'user',
          content: data.content,
          time: Date.now()
        };
        messages.push(msg);

        // Update all agents' memory
        getAgents().forEach(a => updateAgentMemory(a.id, msg));

        broadcast({ type: 'message', ...msg });

        // 通知所有 agent
        getAgents().forEach(agent => {
          const state = agentState[agent.id];
          if (state?.ws && state.ws.readyState === WebSocket.OPEN) {
            setTimeout(() => {
              state.ws.send(JSON.stringify({ type: 'agent_query', message: msg }));
            }, REPLY_DELAY);
          }
        });

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, id: msgId }));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  // 全部消息（带 reactions）
  if (url.pathname === '/api/messages') {
    const result = messages.slice(-200).map(m => ({
      ...m,
      reactions: reactions[m.id] || []
    }));
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ messages: result }));
    return;
  }

  // 在线用户
  if (url.pathname === '/api/online-users') {
    const humanUsers = Object.values(users).filter(u => u.role === 'user');
    const onlineAgents = getAgents().filter(a => agentState[a.id]?.online).map(a => ({
      id: a.id, name: a.name, avatar: a.avatar
    }));
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ users: humanUsers, agents: onlineAgents }));
    return;
  }

  // 导出
  if (url.pathname === '/api/export' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { name } = JSON.parse(body);
        if (messages.length === 0) {
          res.writeHead(400); res.end(JSON.stringify({ error: '没有记录' })); return;
        }
        const filename = (name || 'chat') + '_' + new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19) + '.json';
        const filepath = path.join(DATA_DIR, filename);
        const exportData = {
          name: name || '未命名',
          mode: 'multi-agent',
          exportTime: Date.now(),
          messageCount: messages.length,
          agents: getAgents().map(a => ({ id: a.id, name: a.name, avatar: a.avatar })),
          messages: messages.map(m => ({ ...m, reactions: reactions[m.id] || [] }))
        };
        fs.writeFileSync(filepath, JSON.stringify(exportData, null, 2), 'utf-8');
        const count = messages.length;
        messages.length = 0; msgId = 0;
        // Clear reactions
        Object.keys(reactions).forEach(k => delete reactions[k]);
        broadcast({ type: 'cleared', content: `导出 ${count} 条 → ${filename}`, time: Date.now() });
        res.writeHead(200); res.end(JSON.stringify({ ok: true, filename, count }));
      } catch (e) { res.writeHead(500); res.end(JSON.stringify({ error: e.message })); }
    });
    return;
  }

  // 存档列表
  if (url.pathname === '/api/archives') {
    try {
      const files = fs.readdirSync(DATA_DIR).filter(f => f.endsWith('.json')).sort().reverse();
      const archives = files.map(f => {
        try {
          const d = JSON.parse(fs.readFileSync(path.join(DATA_DIR, f), 'utf-8'));
          return { filename: f, name: d.name, exportTime: d.exportTime, messageCount: d.messageCount, mode: d.mode };
        } catch { return null; }
      }).filter(Boolean);
      res.writeHead(200); res.end(JSON.stringify({ archives }));
    } catch (e) { res.writeHead(500); res.end(JSON.stringify({ error: e.message })); }
    return;
  }

  // 导入
  if (url.pathname === '/api/import' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { filename } = JSON.parse(body);
        const filepath = path.join(DATA_DIR, filename);
        if (!fs.existsSync(filepath)) { res.writeHead(404); res.end(JSON.stringify({ error: '不存在' })); return; }
        const data = JSON.parse(fs.readFileSync(filepath, 'utf-8'));
        res.writeHead(200); res.end(JSON.stringify({ ok: true, messages: data.messages || [], name: data.name }));
      } catch (e) { res.writeHead(500); res.end(JSON.stringify({ error: e.message })); }
    });
    return;
  }

  // 删除存档
  if (url.pathname === '/api/archive/delete' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { filename } = JSON.parse(body);
        const filepath = path.join(DATA_DIR, filename);
        if (fs.existsSync(filepath)) fs.unlinkSync(filepath);
        res.writeHead(200); res.end(JSON.stringify({ ok: true }));
      } catch (e) { res.writeHead(500); res.end(JSON.stringify({ error: e.message })); }
    });
    return;
  }

  // 清空消息
  if (url.pathname === '/api/clear' && req.method === 'POST') {
    const count = messages.length;
    messages.length = 0; msgId = 0;
    Object.keys(reactions).forEach(k => delete reactions[k]);
    broadcast({ type: 'cleared', content: `清空了 ${count} 条消息`, time: Date.now() });
    res.writeHead(200); res.end(JSON.stringify({ ok: true, cleared: count }));
    return;
  }

  // Agent memory endpoint
  if (url.pathname === '/api/agent-memory' && req.method === 'GET') {
    const agentId = url.searchParams.get('id');
    if (!agentId || !agentMemory[agentId]) {
      res.writeHead(404); res.end(JSON.stringify({ error: 'Agent not found' }));
      return;
    }
    res.writeHead(200); res.end(JSON.stringify({ memory: agentMemory[agentId] }));
    return;
  }

  res.writeHead(404); res.end('not found');
});

// ============ WebSocket ============
const wss = new WebSocket.Server({ server });

wss.on('connection', (ws) => {
  let currentUser = null;

  ws.on('message', (raw) => {
    try {
      const data = JSON.parse(raw);
      switch (data.type) {
        case 'join':
          currentUser = { id: 'user_' + (++userIdCounter), name: data.name || '匿名', role: data.role || 'user' };
          users[currentUser.id] = currentUser;
          ws.user = currentUser;

          // Send history with reactions
          const history = messages.slice(-50).map(m => ({
            ...m, reactions: reactions[m.id] || []
          }));
          ws.send(JSON.stringify({ type: 'history', messages: history }));

          // 如果是 agent 连接
          if (data.agentId && agentState[data.agentId]) {
            agentState[data.agentId].online = true;
            agentState[data.agentId].ws = ws;
            agentState[data.agentId].lastSeen = Date.now();
            currentUser.role = data.agentId;
          }

          broadcast({ type: 'system', content: `${currentUser.name} 加入了聊天`, time: Date.now() });

          // Send current agent states
          const agentStatuses = getAgents().map(a => ({
            id: a.id, name: a.name, avatar: a.avatar,
            online: agentState[a.id]?.online || false
          }));
          ws.send(JSON.stringify({ type: 'agent_status', agents: agentStatuses }));
          break;

        case 'message':
          if (!currentUser) return;
          msgId++;
          const msg = {
            id: msgId, from: currentUser.name, fromId: currentUser.id,
            role: currentUser.role, content: data.content, time: Date.now()
          };
          messages.push(msg);
          if (messages.length > MAX_MESSAGES) messages.splice(0, messages.length - MAX_MESSAGES);

          // Update agent memories
          getAgents().forEach(a => updateAgentMemory(a.id, msg));

          broadcast({ type: 'message', ...msg });

          // 通知 agents
          getAgents().forEach(agent => {
            const state = agentState[agent.id];
            if (state?.ws && state.ws.readyState === WebSocket.OPEN && agent.id !== currentUser.role) {
              setTimeout(() => {
                state.ws.send(JSON.stringify({ type: 'agent_query', message: msg }));
              }, REPLY_DELAY);
            }
          });
          break;

        case 'typing':
          // Forward user typing
          if (currentUser) {
            broadcast({
              type: 'typing',
              userId: currentUser.id,
              userName: currentUser.name,
              isTyping: data.isTyping !== false,
              time: Date.now()
            });
          }
          break;

        case 'react':
          // Handle reaction from WebSocket
          if (currentUser && data.msgId && data.emoji) {
            const mid = data.msgId;
            if (!reactions[mid]) reactions[mid] = [];
            const existing = reactions[mid].findIndex(r => r.userId === currentUser.id && r.emoji === data.emoji);
            if (existing >= 0) {
              reactions[mid].splice(existing, 1);
            } else {
              reactions[mid].push({ userId: currentUser.id, emoji: data.emoji, time: Date.now() });
            }
            broadcast({
              type: 'reaction',
              msgId: mid,
              reactions: reactions[mid],
              time: Date.now()
            });
          }
          break;
      }
    } catch (e) { console.error('消息错误:', e.message); }
  });

  ws.on('close', () => {
    if (currentUser) {
      if (agentState[currentUser.role]) {
        agentState[currentUser.role].online = false;
        agentState[currentUser.role].ws = null;
      }
      delete users[currentUser.id];
      broadcast({ type: 'system', content: `${currentUser.name} 离开了聊天`, time: Date.now() });
    }
  });
});

server.listen(PORT, '::', () => {
  const agents = getAgents();
  console.log(`
╔══════════════════════════════════════════════════╗
║   🤖 Multi-Agent Chat Server v2.0                ║
║   http://localhost:${PORT}                          ║
║   Agents: ${agents.map(a => a.avatar + ' ' + a.name).join(', ')}        ║
║   Features: typing, reactions, search, memory     ║
╚══════════════════════════════════════════════════╝
  `);
});
