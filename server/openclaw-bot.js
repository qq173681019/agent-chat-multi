const WebSocket = require('ws');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const configPath = path.join(__dirname, '../config.json');
const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'));

// ===== secrets 注入 (2026-06-07) =====
function loadSecrets() {
  const fs2 = require('fs'), path2 = require('path'), os = require('os');
  const candidates = [
    process.env.AGENT_CHAT_SECRETS,
    path2.join(os.homedir(), '.agent-chat-secrets.json'),
    path2.join(__dirname, '..', 'secrets.json'),
  ];
  for (const p of candidates) {
    if (!p) continue;
    try {
      if (fs2.existsSync(p)) {
        const s = JSON.parse(fs2.readFileSync(p, 'utf-8'));
        if (s.apiKey) return s;
      }
    } catch (e) { /* 静默失败 */ }
  }
  return null;
}
const _secrets = loadSecrets();
if (_secrets) {
  if (!config.apiKey && _secrets.apiKey) config.apiKey = _secrets.apiKey;
  if (!config.apiBase && _secrets.apiBase) config.apiBase = _secrets.apiBase;
}
if (!config.apiKey) {
  console.error('[FATAL] apiKey 未配置。放到 ~/.agent-chat-secrets.json 或设环境变量 AGENT_CHAT_SECRETS');
  process.exit(1);
}
// ===== end secrets =====


const SERVER_URL = config.serverUrl || `ws://localhost:${config.serverPort || 3000}`;
const BOT_NAME = config.botName || '🤖 小呆';
const BOT_ROLE = config.botRole || 'agent-a';

// OpenClaw 配置
const OPENCLAW_PORT = config.openclawPort || 18790;
const OPENCLAW_URL = `http://localhost:${OPENCLAW_PORT}`;

// 用哪个 backend: "openclaw" 用小呆, "api" 用普通API
const BACKEND = config.backend || 'openclaw';

let ws;
let conversationHistory = [];

function connect() {
  console.log(`[Bot] 🤖 ${BOT_NAME} (backend: ${BACKEND})`);
  console.log(`[Bot] 连接到 ${SERVER_URL} ...`);
  ws = new WebSocket(SERVER_URL);
  ws.on('open', () => {
    console.log(`[Bot] ✅ 连接成功`);
    ws.send(JSON.stringify({ type: 'join', name: BOT_NAME, role: BOT_ROLE }));
  });
  ws.on('message', async (raw) => {
    const data = JSON.parse(raw);
    if (data.type === 'agent_query') {
      const userMsg = data.message.content;
      const from = data.message.from;
      console.log(`[Bot] ${from}: ${userMsg}`);
      
      try {
        let reply;
        if (BACKEND === 'openclaw') {
          reply = await askOpenClaw(from, userMsg);
        } else {
          conversationHistory.push({ role: 'user', content: userMsg });
          if (conversationHistory.length > 10) conversationHistory = conversationHistory.slice(-10);
          reply = await callAPI(conversationHistory);
          conversationHistory.push({ role: 'assistant', content: reply });
        }
        
        ws.send(JSON.stringify({ type: 'agent_reply', content: reply, replyTo: data.message.id }));
        console.log(`[Bot] 回复: ${reply.substring(0, 60)}...`);
      } catch (e) {
        console.error('[Bot] 错误:', e.message);
        ws.send(JSON.stringify({ type: 'agent_reply', content: '嗯...脑子卡了一下 🤔 再说一遍？', replyTo: data.message.id }));
      }
    }
  });
  ws.on('close', () => { console.log('[Bot] 断开，3秒后重连...'); setTimeout(connect, 3000); });
  ws.on('error', (e) => console.error('[Bot] 连接错误:', e.message));
}

async function askOpenClaw(from, message) {
  // 通过 OpenClaw REST API 发送消息并获取回复
  // OpenClaw gateway 有 /api/chat 端点
  const payload = JSON.stringify({
    message: `[聊天室] ${from} 对你说: ${message}\n请用简短自然的聊天语气回复（2-3句话以内），不要用markdown格式，就像真人聊天一样。`,
    stream: false
  });

  const cmd = `curl -s --max-time 60 'http://localhost:${OPENCLAW_PORT}/api/chat' -H 'Content-Type: application/json' -d '${payload.replace(/'/g, "'\\''")}'`;
  
  try {
    const result = execSync(cmd, { encoding: 'utf-8', timeout: 65000 });
    // 尝试解析回复
    const data = JSON.parse(result);
    if (data.reply || data.message || data.content) {
      return (data.reply || data.message || data.content).trim();
    }
    if (data.choices && data.choices[0]) {
      return data.choices[0].message.content.trim();
    }
    return result.substring(0, 200).trim();
  } catch (e) {
    // 如果 REST API 不可用，fallback 到直接用 sessions_spawn
    console.log('[Bot] REST API 不可用，尝试 spawn...');
    return await spawnReply(from, message);
  }
}

async function spawnReply(from, message) {
  // 用 openclaw CLI spawn 一个一次性 session
  const prompt = `你是聊天室里的AI角色"${BOT_NAME}"。${from}对你说: ${message}\n请用简短自然的聊天语气回复（2-3句话），不要markdown，像真人聊天。`;
  const cmd = `openclaw run --no-stream --message '${prompt.replace(/'/g, "'\\''")}' 2>/dev/null`;
  
  try {
    const result = execSync(cmd, { encoding: 'utf-8', timeout: 60000 });
    return result.trim() || '让我想想... 🤔';
  } catch (e) {
    throw new Error('OpenClaw 不可用: ' + e.message);
  }
}

async function callAPI(history) {
  const systemPrompt = (config.systemPrompt || '你是{botName}，一个有趣的AI助手。').replace('{botName}', BOT_NAME);
  const msgs = [{ role: 'system', content: systemPrompt }, ...history];
  const body = JSON.stringify({ model: config.model || 'glm-4-flash', messages: msgs, max_tokens: 200, temperature: 0.85 });
  const apiKey = config.apiKey || '';
  const apiBase = config.apiBase || 'https://open.bigmodel.cn/api/paas/v4/chat/completions';
  const useProxy = config.useProxy !== false;
  const proxy = useProxy ? `--proxy ${config.proxy || 'http://127.0.0.1:7897'} ` : '';
  const cmd = `curl -s --max-time 30 ${proxy}${apiBase} -H "Content-Type: application/json" -H "Authorization: Bearer ${apiKey}" -d '${body.replace(/'/g, "'\\''")}'`;
  const result = execSync(cmd, { encoding: 'utf-8', timeout: 35000 });
  const data = JSON.parse(result);
  if (data.choices && data.choices[0]) return data.choices[0].message.content.trim();
  throw new Error('API异常: ' + JSON.stringify(data).substring(0, 100));
}

connect();
