const http = require('http');
const fs = require('fs');
const path = require('path');
const WebSocket = require('ws');

const PORT = 3000;
const DATA_DIR = path.join(__dirname, '../data');

// 确保 data 目录存在
if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

// 消息存储
const messages = [];
let msgId = 0;

const agents = {
  'agent-a': { name: 'Agent A (小呆)', online: false, ws: null },
  'agent-b': { name: 'Agent B (同事)', online: false, ws: null }
};
const users = {};
let userIdCounter = 0;

// HTTP 服务
const server = http.createServer((req, res) => {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  const url = new URL(req.url, `http://${req.headers.host}`);

  // 前端页面
  if (url.pathname === '/' || url.pathname === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(fs.readFileSync(path.join(__dirname, '../public/index.html')));
    return;
  }

  // 获取配置（前端用，不暴露 apiKey）
  if (url.pathname === "/api/config") {
    try {
      const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, "../config.json"), "utf-8"));
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ botName: cfg.botName || "🤖 Agent", model: cfg.model || "" }));
    } catch (e) {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ botName: "🤖 Agent", model: "" }));
    }
    return;
  }
  
  // 获取待处理的 Agent 消息（轮询用）
  if (url.pathname === '/api/poll' && req.method === 'GET') {
    const since = parseInt(url.searchParams.get('since') || '0');
    const pending = messages.filter(m => m.id > since && m.role !== 'system');
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ messages: pending, lastId: msgId }));
    return;
  }

  // Agent 通过 API 发送回复
  if (url.pathname === '/api/reply' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        msgId++;
        const reply = { id: msgId, from: data.from || '小呆', fromId: 'openclaw', role: data.role || 'agent-a', content: data.content, time: Date.now() };
        messages.push(reply);
        broadcast({ type: 'message', ...reply });
        
        // 如果有另一个 Agent 在线，也通知它
        const otherRole = reply.role === 'agent-a' ? 'agent-b' : 'agent-a';
        const otherAgent = agents[otherRole];
        if (otherAgent && otherAgent.ws && otherAgent.ws.readyState === WebSocket.OPEN) {
          setTimeout(() => {
            otherAgent.ws.send(JSON.stringify({ type: 'agent_query', message: reply, agent_role: otherRole }));
          }, 2000);
        }
        
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, id: msgId }));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  // 获取消息
  if (url.pathname === '/api/messages') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ messages: messages.slice(-100) }));
    return;
  }

  // 导出聊天记录
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

        // 清空内存中的消息
        const count = messages.length;
        messages.length = 0;
        msgId = 0;

        // 通知所有客户端聊天记录已清空
        broadcast({ type: 'cleared', content: `导出了 ${count} 条消息 → ${filename}`, time: Date.now() });

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, filename, count }));
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  // 获取已保存的聊天记录列表
  if (url.pathname === '/api/archives') {
    try {
      const files = fs.readdirSync(DATA_DIR).filter(f => f.endsWith('.json')).sort().reverse();
      const archives = files.map(f => {
        try {
          const data = JSON.parse(fs.readFileSync(path.join(DATA_DIR, f), 'utf-8'));
          return {
            filename: f,
            name: data.name,
            exportTime: data.exportTime,
            messageCount: data.messageCount
          };
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

  // 导入聊天记录
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

  // 删除存档
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

// WebSocket
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
          ws.send(JSON.stringify({ type: 'history', messages: messages.slice(-50) }));
          broadcast({ type: 'system', content: `${currentUser.name} 加入了聊天`, time: Date.now() });
          if (currentUser.role === 'agent-a' || currentUser.role === 'agent-b') {
            agents[currentUser.role].online = true;
            agents[currentUser.role].ws = ws;
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
              if (agent.ws && agent.ws.readyState === WebSocket.OPEN) {
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
          // 通知另一个 Agent（AI 对 AI 对话）
          const otherRole = currentUser.role === 'agent-a' ? 'agent-b' : 'agent-a';
          const otherAgent = agents[otherRole];
          if (otherAgent && otherAgent.ws && otherAgent.ws.readyState === WebSocket.OPEN) {
            // 延迟2秒，避免两个 AI 无限互聊
            setTimeout(() => {
              otherAgent.ws.send(JSON.stringify({
                type: 'agent_query',
                message: reply,
                agent_role: otherRole
              }));
            }, 2000);
          }
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
});

function broadcast(data) {
  const raw = JSON.stringify(data);
  wss.clients.forEach(client => { if (client.readyState === WebSocket.OPEN) client.send(raw); });
}

server.listen(PORT, '::', () => {
  console.log(`\n╔══════════════════════════════════════╗\n║   Agent Chat Server                  ║\n║   http://localhost:${PORT}              ║\n╚══════════════════════════════════════╝\n`);
});
