const WebSocket = require('ws');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const http = require('http');
const https = require('https');
const { URL } = require('url');

// 支持 env 指定不同 config (用于跑多个 agent 实例)
const configPath = process.env.AGENT_CONFIG_PATH || path.join(__dirname, '../config.json');
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
        if (s.apiKey || s.minimaxApiKey) return s;
      }
    } catch (e) { /* 静默失败 */ }
  }
  return null;
}
const _secrets = loadSecrets();
if (_secrets) {
  if (!config.apiKey && _secrets.apiKey) config.apiKey = _secrets.apiKey;
  if (!config.apiBase && _secrets.apiBase) config.apiBase = _secrets.apiBase;
  if (!config.minimaxApiKey && _secrets.minimaxApiKey) config.minimaxApiKey = _secrets.minimaxApiKey;
  if (!config.minimaxBase && _secrets.minimaxBase) config.minimaxBase = _secrets.minimaxBase;
}
if (!config.apiKey && !config.minimaxApiKey) {
  console.error('[FATAL] 既无 zhipu apiKey 也无 minimax apiKey。放到 ~/.agent-chat-secrets.json');
  process.exit(1);
}
// ===== end secrets =====

const SERVER_URL = config.serverUrl || `ws://localhost:${config.serverPort || 3000}`;
const BOT_NAME = config.botName || '🤖 Agent';
const BOT_ROLE = config.botRole || 'agent-a';
const FALLBACK_PREFIX = config.fallbackPrefix || '傻傻的';  // 兜底模型回复时加在 from 前
// 模型链: 首选 + 兜底. 第一个调失败就试下一个.
const MODELS = [config.model, ...(config.fallbackModels || [])].filter(Boolean);
const PRIMARY_MODEL = MODELS[0];
const SYSTEM_PROMPT = (config.systemPrompt || '你是{botName}，一个有趣的AI助手。').replace('{botName}', BOT_NAME);
const MAX_TOKENS = config.maxTokens || 200;
const TEMPERATURE = config.temperature || 0.85;
const MAX_HISTORY = config.maxHistory || 10;

let ws;
let conversationHistory = [];
let currentTurnModel = PRIMARY_MODEL;  // 当前回复用的模型, 给 agent_query 的回复用

function connect() {
  console.log(`[Agent] ${BOT_NAME} (${BOT_ROLE}) models=${MODELS.join(' -> ')}`);
  console.log(`[Agent] 连接到 ${SERVER_URL} ...`);
  ws = new WebSocket(SERVER_URL);
  ws.on('open', () => {
    console.log(`[Agent] ✅ 连接成功`);
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
        const result = await callLLMWithFallback(conversationHistory);
        currentTurnModel = result.model;
        const isFallback = result.model !== PRIMARY_MODEL;
        const prefix = isFallback ? FALLBACK_PREFIX : '';
        const reply = {
          type: 'agent_reply',
          content: result.text,
          replyTo: data.message.id,
          fromPrefix: prefix || undefined  // undefined 让 server 端不处理
        };
        ws.send(JSON.stringify(reply));
        conversationHistory.push({ role: 'assistant', content: result.text });
        console.log(`[Agent] 回复 (${result.model}${isFallback ? ' ⚠️FALLBACK' : ''}): ${result.text.substring(0, 60)}`);
      } catch (e) {
        console.error('[Agent] 全部模型都失败:', e.message);
        currentTurnModel = PRIMARY_MODEL;
        // 全部失败: 不加前缀 (这不是 fallback, 是 catch-all 兜底句)
        ws.send(JSON.stringify({ type: 'agent_reply', content: '嗯...脑子卡了一下 🤔', replyTo: data.message.id }));
      }
    }
  });
  ws.on('close', () => { console.log('[Agent] 断开，3秒后重连...'); setTimeout(connect, 3000); });
  ws.on('error', (e) => console.error('[Agent] 连接错误:', e.message));
}

// 按顺序尝试 MODELS, 第一个成功的就返回
async function callLLMWithFallback(history) {
  let lastErr = null;
  for (let i = 0; i < MODELS.length; i++) {
    const m = MODELS[i];
    const fmt = m.toLowerCase().includes('minimax') ? 'anthropic' : 'openai';
    try {
      const text = fmt === 'anthropic' ? await callAnthropic(history, m) : await callOpenAI(history, m);
      return { text, model: m };
    } catch (e) {
      console.error(`[Agent] ${m} (${fmt}) 失败: ${e.message.substring(0, 120)}`);
      lastErr = e;
      // 继续试下一个
    }
  }
  throw lastErr || new Error('no models configured');
}

async function callAnthropic(history, modelName) {
  const apiKey = config.minimaxApiKey;
  const apiBase = config.minimaxBase || 'https://api.minimaxi.com/anthropic';
  const url = new URL(`${apiBase}/v1/messages`);
  const msgs = history.map(h => ({ role: h.role, content: h.content }));
  const body = JSON.stringify({
    model: modelName,
    max_tokens: MAX_TOKENS,
    temperature: TEMPERATURE,
    system: SYSTEM_PROMPT,
    messages: msgs
  });
  return new Promise((resolve, reject) => {
    const req = https.request({
      method: 'POST',
      hostname: url.hostname,
      path: url.pathname,
      headers: {
        'Content-Type': 'application/json',
        'anthropic-version': '2023-06-01',
        'x-api-key': apiKey,
        'Content-Length': Buffer.byteLength(body)
      }
    }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (parsed.error) return reject(new Error('Anthropic: ' + (parsed.error.message || JSON.stringify(parsed.error))));
          if (parsed.content && Array.isArray(parsed.content)) {
            const text = parsed.content.filter(c => c.type === 'text').map(c => c.text).join('\n').trim();
            if (text) return resolve(text);
            const think = parsed.content.filter(c => c.type === 'thinking').map(c => c.thinking).join('\n').trim();
            if (think) return resolve(think);
          }
          reject(new Error('Anthropic 解析失败: ' + JSON.stringify(parsed).substring(0, 200)));
        } catch (e) { reject(new Error('JSON parse: ' + e.message + ' | ' + data.substring(0, 200))); }
      });
    });
    req.on('error', reject);
    req.setTimeout(35000, () => req.destroy(new Error('timeout')));
    req.write(body);
    req.end();
  });
}

async function callOpenAI(history, modelName) {
  const msgs = [{ role: 'system', content: SYSTEM_PROMPT }, ...history];
  const body = JSON.stringify({ model: modelName, messages: msgs, max_tokens: MAX_TOKENS, temperature: TEMPERATURE });
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

console.log(`[Agent] 🤖 ${BOT_NAME} / ${MODELS[0]} (fallback: ${MODELS.slice(1).join(',') || '无'})`);
connect();
