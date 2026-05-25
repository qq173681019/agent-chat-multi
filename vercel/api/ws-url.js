// Vercel Serverless Function: 获取 WebSocket 地址
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
  
  if (req.method === 'OPTIONS') return res.status(204).end();

  return res.status(200).json({
    url: 'https://conflicts-albert-commission-salt.trycloudflare.com',
    updated: Date.now()
  });
}
