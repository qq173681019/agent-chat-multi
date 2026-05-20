import { put, head } from '@vercel/blob';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
  
  if (req.method === 'OPTIONS') return res.status(204).end();

  // POST: 更新 WebSocket 地址
  if (req.method === 'POST') {
    const auth = req.headers.authorization;
    const secret = process.env.ADMIN_SECRET || 'changeme';
    if (auth !== `Bearer ${secret}`) {
      return res.status(403).json({ error: 'forbidden' });
    }
    const { url } = req.body || {};
    if (!url || !url.match(/^https?:\/\//)) {
      return res.status(400).json({ error: 'invalid url' });
    }
    await put('ws-url.json', JSON.stringify({ url, updated: Date.now() }), { access: 'public' });
    return res.status(200).json({ ok: true, url });
  }

  // GET: 获取 WebSocket 地址
  try {
    const blobInfo = await head('ws-url.json');
    if (blobInfo) {
      const resp = await fetch(blobInfo.url);
      const data = await resp.json();
      return res.status(200).json(data);
    }
  } catch (e) {}
  
  // fallback: 环境变量
  return res.status(200).json({ 
    url: process.env.DEFAULT_WS_URL || '',
    updated: null 
  });
}
