const http = require('http');
const fs = require('fs');
const path = require('path');
const WebSocket = require('ws');

const PORT = 3000;
const DATA_DIR = path.join(__dirname, '../data');

if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

const messages = [];
let msgId = 0;
const agents = {
  'agent-a': { name: 'Agent A', online: false, ws: null },
  'agent-b': { name: 'Agent B', online: false, ws: null }
};
const users = {};
let userIdCounter = 0;
const reactions = {};
const typingState = {};

// Load config
let botConfig = {};
try {
  botConfig = JSON.parse(fs.readFileSync(path.join(__dirname, '../config.json'), 'utf-8'));
  if (botConfig.botName) agents['agent-a'].name = botConfig.botName;
} catch (e) {}

// Helpers
function broadcast(data) {
  const raw = JSON.stringify(data);
  const wssClients = module.exports?.wss?.clients;
  if (wssClients) wssClients.forEach(c => { if (c.readyState === WebSocket.OPEN) c.send(raw); });
}

const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  const url = new URL(req.url, `http://${req.headers.host}`);

  // Frontend
  if (url.pathname === '/' || url.pathname === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(fs.readFileSync(path.join(__dirname, '../public/index.html')));
    return;
  }

  // Config
  if (url.pathname === '/api/config') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      botName: botConfig.botName || '🤖 Agent',
      model: botConfig.model || '',
      mode: 'dual',
      agentCount: 2,
      agents: [
        { id: 'agent-a', name: agents['agent-a'].name },
        { id: 'agent-b', name: agents['agent-b'].name }
      ]
    }));
    return;
  }

  // Health
  if (url.pathname === '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      status: 'ok', uptime: process.uptime(),
      messageCount: messages.length, mode: 'dual',
      agents: Object.entries(agents).map(([id, a]) => ({ id, name: a.name, online: a.online })),
      users: Object.keys(users).length,
      timestamp: Date.now()
    }));
    return;
  }

  // Poll
  if (url.pathname === '/api/poll' && req.method === 'GET') {
    const since = parseInt(url.searchParams.get('since') || '0');
    const pending = messages.filter(m => m.id > since && m.role !== 'system');
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ messages: pending, lastId: msgId }));
    return;
  }

  // Reply (agent API)
  if (url.pathname === '/api/reply' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        msgId++;
        const reply = { id: msgId, from: data.from || 'Agent', fromId: 'openclaw', role: data.role || 'agent-a', content: data.content, time: Date.now() };
        messages.push(reply);
        if (messages.length > 500) messages.shift();
        
        // Update agent state
        if (agents[reply.role]) agents[reply.role].online = true;
        
        // Clear typing
        if (typingState[reply.role]) { clearTimeout(typingState[reply.role]); delete typingState[reply.role]; broadcast({ type: 'typing', agentId: reply.role, agentName: agents[reply.role]?.name, isTyping: false }); }
        
        broadcast({ type: 'message', ...reply });

        // Notify other agent
        const otherRole = reply.role === 'agent-a' ? 'agent-b' : 'agent-a';
        const otherAgent = agents[otherRole];
        if (otherAgent?.ws?.readyState === WebSocket.OPEN) {
          setTimeout(() => otherAgent.ws.send(JSON.stringify({ type: 'agent_query', message: reply, agent_role: otherRole })), 2000);
        }

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, id: msgId }));
      } catch (e) { res.writeHead(400); res.end(JSON.stringify({ error: e.message })); }
    });
    return;
  }

  // Typing
  if (url.pathname === '/api/typing' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        const role = data.role || data.agentId;
        broadcast({ type: 'typing', agentId: role, agentName: agents[role]?.name || data.from, isTyping: data.isTyping !== false });
        if (data.isTyping !== false) {
          if (typingState[role]) clearTimeout(typingState[role]);
          typingState[role] = setTimeout(() => broadcast({ type: 'typing', agentId: role, agentName: agents[role]?.name, isTyping: false }), 10000);
        }
        res.writeHead(200); res.end(JSON.stringify({ ok: true }));
      } catch(e) { res.writeHead(400); res.end(JSON.stringify({ error: e.message })); }
    });
    return;
  }

  // Search
  if (url.pathname === '/api/search' && req.method === 'GET') {
    const q = (url.searchParams.get('q') || '').toLowerCase();
    const limit = Math.min(parseInt(url.searchParams.get('limit') || '20'), 50);
    if (!q) { res.writeHead(400); res.end(JSON.stringify({ error: 'Missing q' })); return; }
    const results = messages.filter(m => m.content?.toLowerCase().includes(q)).slice(-limit);
    res.writeHead(200); res.end(JSON.stringify({ results, total: results.length }));
    return;
  }

  // Messages
  if (url.pathname === '/api/messages') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ messages: messages.slice(-100) }));
    return;
  }

  // Online users
  if (url.pathname === '/api/online-users') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ users: Object.values(users).filter(u => u.role === 'user') }));
    return;
  }

  // Export
  if (url.pathname === '/api/export' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { name } = JSON.parse(body);
        if (!messages.length) { res.writeHead(400); res.end(JSON.stringify({ error: '没有记录' })); return; }
        const filename = (name || 'chat') + '_' + new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19) + '.json';
        fs.writeFileSync(path.join(DATA_DIR, filename), JSON.stringify({ name: name || '未命名', mode: 'dual', exportTime: Date.now(), messageCount: messages.length, messages }, null, 2), 'utf-8');
        const count = messages.length;
        messages.length = 0; msgId = 0;
        broadcast({ type: 'cleared', content: `导出 ${count} 条 → ${filename}`, time: Date.now() });
        res.writeHead(200); res.end(JSON.stringify({ ok: true, filename, count }));
      } catch (e) { res.writeHead(500); res.end(JSON.stringify({ error: e.message })); }
    });
    return;
  }

  // Archives
  if (url.pathname === '/api/archives') {
    try {
      const files = fs.readdirSync(DATA_DIR).filter(f => f.endsWith('.json')).sort().reverse();
      const archives = files.map(f => { try { const d = JSON.parse(fs.readFileSync(path.join(DATA_DIR, f), 'utf-8')); return { filename: f, name: d.name, exportTime: d.exportTime, messageCount: d.messageCount }; } catch { return null; } }).filter(Boolean);
      res.writeHead(200); res.end(JSON.stringify({ archives }));
    } catch (e) { res.writeHead(500); res.end(JSON.stringify({ error: e.message })); }
    return;
  }

  // Import
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

  // Delete archive
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

  // Clear
  if (url.pathname === '/api/clear' && req.method === 'POST') {
    const count = messages.length;
    messages.length = 0; msgId = 0;
    Object.keys(reactions).forEach(k => delete reactions[k]);
    broadcast({ type: 'cleared', content: `清空了 ${count} 条消息`, time: Date.now() });
    res.writeHead(200); res.end(JSON.stringify({ ok: true, cleared: count }));
    return;
  }

  res.writeHead(404); res.end('not found');
});

// WebSocket
const wss = new WebSocket.Server({ server });
module.exports.wss = wss;

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
          ws.send(JSON.stringify({ type: 'history', messages: messages.slice(-50) }));
          broadcast({ type: 'system', content: `${currentUser.name} 加入了聊天`, time: Date.now() });
          if (data.role === 'agent-a' || data.role === 'agent-b') {
            agents[data.role].online = true;
            agents[data.role].ws = ws;
          }
          break;
        case 'message':
          if (!currentUser) return;
          msgId++;
          const msg = { id: msgId, from: currentUser.name, fromId: currentUser.id, role: currentUser.role, content: data.content, time: Date.now() };
          messages.push(msg);
          if (messages.length > 500) messages.shift();
          broadcast({ type: 'message', ...msg });
          if (currentUser.role === 'user') {
            Object.values(agents).forEach(agent => {
              if (agent.ws?.readyState === WebSocket.OPEN) {
                agent.ws.send(JSON.stringify({ type: 'agent_query', message: msg, agent_role: agent === agents['agent-a'] ? 'agent-a' : 'agent-b' }));
              }
            });
          }
          break;
        case 'agent_reply':
          if (!currentUser) return;
          msgId++;
          const reply = { id: msgId, from: currentUser.name, fromId: currentUser.id, role: currentUser.role, content: data.content, replyTo: data.replyTo || null, time: Date.now() };
          messages.push(reply);
          broadcast({ type: 'message', ...reply });
          const otherRole = currentUser.role === 'agent-a' ? 'agent-b' : 'agent-a';
          const otherAgent = agents[otherRole];
          if (otherAgent?.ws?.readyState === WebSocket.OPEN) {
            setTimeout(() => otherAgent.ws.send(JSON.stringify({ type: 'agent_query', message: reply, agent_role: otherRole })), 2000);
          }
          break;
      }
    } catch (e) { console.error('Parse error:', e.message); }
  });

  ws.on('close', () => {
    if (currentUser) {
      if (agents[currentUser.role]) { agents[currentUser.role].online = false; agents[currentUser.role].ws = null; }
      delete users[currentUser.id];
      broadcast({ type: 'system', content: `${currentUser.name} 离开了聊天`, time: Date.now() });
    }
  });
});

server.listen(PORT, '::', () => {
  console.log(`
╔══════════════════════════════════════╗
║   🤖 Agent Chat Server v2.0          ║
║   http://localhost:${PORT}              ║
║   Mode: Dual Agent                   ║
╚══════════════════════════════════════╝
  `);
});
