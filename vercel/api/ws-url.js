// Vercel Serverless Function: 获取 WebSocket 地址
// 从 GitHub raw 读取，加时间戳防缓存

const GITHUB_RAW_URL = 'https://cdn.jsdelivr.net/gh/qq173681019/agent-chat/ws-url.json';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
  
  if (req.method === 'OPTIONS') return res.status(204).end();

  try {
    const resp = await fetch(GITHUB_RAW_URL + '?t=' + Date.now(), {
      headers: { 'Cache-Control': 'no-cache' }
    });
    if (resp.ok) {
      const data = await resp.json();
      return res.status(200).json(data);
    }
  } catch (e) {}
  
  return res.status(200).json({ url: '', updated: null });
}
