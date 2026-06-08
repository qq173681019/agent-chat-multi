const http = require('http');
const fs = require('fs');
const path = require('path');
const WebSocket = require('ws');

const PORT = 3000;
const DATA_DIR = path.join(__dirname, '../data');
const MESSAGES_LOG = path.join(DATA_DIR, 'messages.log');
const MAX_IN_MEMORY = 500;
const WS_PING_INTERVAL_MS = 30_000;
const WS_PING_TIMEOUT_MS = 60_000;

if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

// ============ 消息持久化 (JSONL append-only) ============
const messages = [];
let msgId = 0;
let writeQueue = Promise.resolve();

function loadMessagesFromLog() {
  if (!fs.existsSync(MESSAGES_LOG)) return;
  try {
    const content = fs.readFileSync(MESSAGES_LOG, 'utf-8');
    const lines = content.split('\n').filter(Boolean);
    const start = Math.max(0, lines.length - MAX_IN_MEMORY);
    for (let i = start; i < lines.length; i++) {
      try {
        const m = JSON.parse(lines[i]);
        messages.push(m);
        if (m.id > msgId) msgId = m.id;
      } catch (e) {
        console.error('[消息日志] 跳过损坏行:', lines[i].slice(0, 80));
      }
    }
    console.log(`[消息日志] 从 ${MESSAGES_LOG} 加载 ${messages.length} 条，最后 id=${msgId}`);
  } catch (e) {
    console.error('[消息日志] 加载失败:', e.message);
  }
}

function persistMessage(msg) {
  writeQueue = writeQueue.then(() => new Promise((resolve) => {
    fs.appendFile(MESSAGES_LOG, JSON.stringify(msg) + '\n', (err) => {
      if (err) console.error('[消息日志] 写入失败:', err.message);
      resolve();
    });
  })).catch(() => {});
}

loadMessagesFromLog();

const agents = {
  'agent-a': { name: 'Agent A (小呆)', online: false, ws: null },
  'agent-b': { name: 'Agent B (同事)', online: false, ws: null }
};
const users = {};
let userIdCounter = 0;

// ============ HTTP ============
const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  const url = new URL(req.url, `http://${req.headers.host}`);

  // (2026-06-08) HTML 路径防浏览器缓存旧 JS
  if (url.pathname === '/' || url.pathname.endsWith('.html')) {
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
  }

  if (url.pathname === '/' || url.pathname === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(fs.readFileSync(path.join(__dirname, '../public/index.html')));
    return;
  }
  // (2026-06-08) 静态文件路由: /diag.html /favicon.ico 等
  if (url.pathname.endsWith('.html') || url.pathname.endsWith('.ico') || url.pathname.endsWith('.js') || url.pathname.endsWith('.css')) {
    const fp = path.join(__dirname, '../public', url.pathname);
    if (fs.existsSync(fp)) {
      const ext = path.extname(url.pathname);
      const ct = ext === '.html' ? 'text/html; charset=utf-8' :
                 ext === '.js' ? 'application/javascript; charset=utf-8' :
                 ext === '.css' ? 'text/css; charset=utf-8' :
                 ext === '.ico' ? 'image/x-icon' : 'application/octet-stream';
      res.writeHead(200, { 'Content-Type': ct, 'Cache-Control': 'no-cache' });
      res.end(fs.readFileSync(fp));
      return;
    }
  }

  if (url.pathname === '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true, msgId, inMemory: messages.length, uptime: process.uptime() }));
    return;
  }
  if (url.pathname === '/api/diag') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      ok: true, msgId, inMemory: messages.length, uptime: process.uptime(),
      pid: process.pid, nodeVersion: process.version, platform: process.platform,
      agents: {
        'agent-a': { online: !!(agents['agent-a'] && agents['agent-a'].ws), name: agents['agent-a']?.name || null },
        'agent-b': { online: !!(agents['agent-b'] && agents['agent-b'].ws), name: agents['agent-b']?.name || null }
      },
      wsClients: wss.clients.size, port: 3000
    }));
    return;
  }

  if (url.pathname === "/api/config") {
    try {
      const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, "../config.json"), "utf-8"));
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({
        botName: cfg.botName || "🤖 Agent",
        model: cfg.model || "",
        botRole: cfg.botRole || "agent-a"
      }));
    } catch (e) {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ botName: "🤖 Agent", model: "" }));
    }
    return;
  }

  if (url.pathname === "/api/online-users" && req.method === 'GET') {
    const humanUsers = Object.values(users).filter(u => u.role === 'user');
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ users: humanUsers }));
    return;
  }

  if (url.pathname === '/api/poll' && req.method === 'GET') {
    const since = parseInt(url.searchParams.get('since') || '0');
    const pending = messages.filter(m => m.id > since && m.role !== 'system');
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ messages: pending, lastId: msgId }));
    return;
  }

  if (url.pathname === '/api/reply' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        msgId++;
        const reply = { id: msgId, from: data.from || '小呆', fromId: 'openclaw', role: data.role || 'agent-a', content: data.content, time: Date.now() };
        messages.push(reply);
        if (messages.length > MAX_IN_MEMORY) messages.shift();
        persistMessage(reply);
        broadcast({ type: 'message', ...reply });
          // (2026-06-07) 不再自动推 agent_query — 避免 agent 无限互聊循环
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, id: msgId }));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  if (url.pathname === '/api/messages') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ messages: messages.slice(-100) }));
    return;
  }

  if (url.pathname === '/api/export' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { name } = JSON.parse(body);
        if (messages.length === 0) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: '没有聊天记录可导出' }));
          return;
        }
        const filename = (name || 'chat') + '_' + new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19) + '.json';
        const filepath = path.join(DATA_DIR, filename);
        const exportData = {
          name: name || '未命名',
          exportTime: Date.now(),
          messageCount: messages.length,
          messages: messages.map(m => ({ ...m }))
        };
        fs.writeFileSync(filepath, JSON.stringify(exportData, null, 2), 'utf-8');
        broadcast({ type: 'system', content: `📦 导出了 ${messages.length} 条 → ${filename}`, time: Date.now() });
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, filename, count: messages.length }));
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  if (url.pathname === '/api/archives') {
    try {
      const files = fs.readdirSync(DATA_DIR).filter(f => f.endsWith('.json') && f !== 'messages.log').sort().reverse();
      const archives = files.map(f => {
        try {
          const data = JSON.parse(fs.readFileSync(path.join(DATA_DIR, f), 'utf-8'));
          return { filename: f, name: data.name, exportTime: data.exportTime, messageCount: data.messageCount };
        } catch { return null; }
      }).filter(Boolean);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ archives }));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
    return;
  }

  if (url.pathname === '/api/import' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { filename } = JSON.parse(body);
        const filepath = path.join(DATA_DIR, filename);
        if (!fs.existsSync(filepath)) {
          res.writeHead(404, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: '文件不存在' }));
          return;
        }
        const data = JSON.parse(fs.readFileSync(filepath, 'utf-8'));
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, messages: data.messages || [], name: data.name }));
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  if (url.pathname === '/api/archive/delete' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { filename } = JSON.parse(body);
        const filepath = path.join(DATA_DIR, filename);
        if (fs.existsSync(filepath)) fs.unlinkSync(filepath);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true }));
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  res.writeHead(404);
  res.end('not found');
});

// ============ WebSocket + KeepAlive ============
const wss = new WebSocket.Server({ server });

function heartbeat() { this.alive = true; }

wss.on('connection', (ws) => {
  ws.alive = true;
  let currentUser = null;

  ws.on('pong', heartbeat);

  ws.on('message', (raw) => {
    try {
      const data = JSON.parse(raw);
      switch (data.type) {
        case 'join':
          currentUser = { id: 'user_' + (++userIdCounter), name: data.name || '匿名', role: data.role || 'user' };
          users[currentUser.id] = currentUser;
          ws.user = currentUser;
          ws.send(JSON.stringify({ type: 'history', messages: messages.slice(-50) }));
          broadcast({ type: 'system', content: `${currentUser.name} 加入了聊天`, time: Date.now() });
          if (currentUser.role === 'agent-a' || currentUser.role === 'agent-b') {
            agents[currentUser.role].online = true;
            agents[currentUser.role].ws = ws;
            agents[currentUser.role].name = currentUser.name;  // (2026-06-08) 同步真名, 不然 /api/diag 一直显示 'Agent A (小呆)'
          }
          break;
        case 'message':
          if (!currentUser) return;
          msgId++;
          const msg = { id: msgId, from: currentUser.name, fromId: currentUser.id, role: currentUser.role, content: data.content, time: Date.now() };
          messages.push(msg);
          if (messages.length > MAX_IN_MEMORY) messages.shift();
          persistMessage(msg);
          broadcast({ type: 'message', ...msg });
          if (currentUser.role === 'user') {
            Object.values(agents).forEach(agent => {
              if (agent.ws && agent.ws.readyState === WebSocket.OPEN) {
                agent.ws.send(JSON.stringify({ type: 'agent_query', message: msg, agent_role: agent === agents['agent-a'] ? 'agent-a' : 'agent-b' }));
              }
            });
          }
          break;
        case 'agent_reply':
          if (!currentUser) return;
          msgId++;
          const reply = { id: msgId, from: (data.fromPrefix || "") + currentUser.name, fromId: currentUser.id, role: currentUser.role, content: data.content, replyTo: data.replyTo || null, time: Date.now() };
          messages.push(reply);
          if (messages.length > MAX_IN_MEMORY) messages.shift();
          persistMessage(reply);
          broadcast({ type: 'message', ...reply });
          // (2026-06-07) 不再自动推 agent_query — 避免 agent 无限互聊循环
          break;
      }
    } catch (e) { console.error('消息解析错误:', e.message); }
  });

  ws.on('close', () => {
    if (currentUser) {
      if (currentUser.role === 'agent-a' || currentUser.role === 'agent-b') {
        agents[currentUser.role].online = false;
        agents[currentUser.role].ws = null;
      }
      delete users[currentUser.id];
      broadcast({ type: 'system', content: `${currentUser.name} 离开了聊天`, time: Date.now() });
    }
  });

  ws.on('error', (e) => { console.error('WS error:', e.message); });
});

// 全局 ping 循环：30s 一次，60s 不回 pong 的连接直接 terminate
const pingInterval = setInterval(() => {
  wss.clients.forEach((ws) => {
    if (ws.alive === false) {
      console.log(`[WS] 踢掉无响应连接 (${ws.user ? ws.user.name : '匿名'})`);
      return ws.terminate();
    }
    ws.alive = false;
    try { ws.ping(); } catch (e) { /* ignore */ }
  });
}, WS_PING_INTERVAL_MS);

wss.on('close', () => clearInterval(pingInterval));

function broadcast(data) {
  const raw = JSON.stringify(data);
  wss.clients.forEach(client => { if (client.readyState === WebSocket.OPEN) client.send(raw); });
}

server.listen(PORT, '::', () => {
  console.log(`\n╔══════════════════════════════════════╗`);
  console.log(`║   Agent Chat Server                  ║`);
  console.log(`║   http://localhost:${PORT}              ║`);
  console.log(`║   持久化: data/messages.log           ║`);
  console.log(`║   WS 保活: ${WS_PING_INTERVAL_MS/1000}s ping / ${WS_PING_TIMEOUT_MS/1000}s timeout   ║`);
  console.log(`╚══════════════════════════════════════╝\n`);
});
