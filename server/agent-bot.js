const WebSocket = require('ws');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const configPath = path.join(__dirname, '../config.json');
const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'));

const SERVER_URL = config.serverUrl || `ws://localhost:${config.serverPort || 3000}`;
const BOT_NAME = config.botName || '🤖 Agent';
const BOT_ROLE = config.botRole || 'agent-a';
const MODEL = config.model || 'glm-4-flash';
const SYSTEM_PROMPT = (config.systemPrompt || '你是{botName}，一个有趣的AI助手。').replace('{botName}', BOT_NAME);
const MAX_TOKENS = config.maxTokens || 200;
const TEMPERATURE = config.temperature || 0.85;
const MAX_HISTORY = config.maxHistory || 10;

let ws;
let conversationHistory = [];

function connect() {
  console.log(`[Agent] 连接到 ${SERVER_URL} ...`);
  ws = new WebSocket(SERVER_URL);
  ws.on('open', () => {
    console.log(`[Agent] ✅ 连接成功，身份: ${BOT_NAME} (${BOT_ROLE})`);
    ws.send(JSON.stringify({ type: 'join', name: BOT_NAME, role: BOT_ROLE }));
  });
  ws.on('message', async (raw) => {
    const data = JSON.parse(raw);
    if (data.type === 'agent_query') {
      const userMsg = data.message.content;
      const from = data.message.from;
      console.log(`[Agent] ${from}: ${userMsg}`);
      conversationHistory.push({ role: 'user', content: userMsg });
      if (conversationHistory.length > MAX_HISTORY) conversationHistory = conversationHistory.slice(-MAX_HISTORY);
      try {
        const reply = await callGLM(conversationHistory);
        ws.send(JSON.stringify({ type: 'agent_reply', content: reply, replyTo: data.message.id }));
        conversationHistory.push({ role: 'assistant', content: reply });
        console.log(`[Agent] 回复: ${reply.substring(0, 60)}`);
      } catch (e) {
        console.error('[Agent] 错误:', e.message);
        ws.send(JSON.stringify({ type: 'agent_reply', content: '嗯...脑子卡了一下 🤔', replyTo: data.message.id }));
      }
    }
  });
  ws.on('close', () => { console.log('[Agent] 断开，3秒后重连...'); setTimeout(connect, 3000); });
  ws.on('error', (e) => console.error('[Agent] 连接错误:', e.message));
}

async function callGLM(history) {
  const msgs = [{ role: 'system', content: SYSTEM_PROMPT }, ...history];
  const body = JSON.stringify({ model: MODEL, messages: msgs, max_tokens: MAX_TOKENS, temperature: TEMPERATURE });
  const apiKey = process.env.LLM_API_KEY || config.apiKey || '';
  const apiBase = config.apiBase || 'https://open.bigmodel.cn/api/paas/v4/chat/completions';
  const useProxy = config.useProxy !== false;
  const proxy = config.proxy || 'http://127.0.0.1:7897';
  const proxyArg = useProxy ? `--proxy ${proxy} ` : '';
  const cmd = `curl -s --max-time 30 ${proxyArg}${apiBase} -H "Content-Type: application/json" -H "Authorization: Bearer ${apiKey}" -d '${body.replace(/'/g, "'\\''")}'`;
  const result = execSync(cmd, { encoding: 'utf-8', timeout: 35000 });
  const data = JSON.parse(result);
  if (data.choices && data.choices[0]) return data.choices[0].message.content.trim();
  throw new Error('API异常: ' + JSON.stringify(data).substring(0, 100));
}

console.log(`[Agent] 🤖 ${BOT_NAME} / ${MODEL}`);
connect();
