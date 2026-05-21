#!/bin/bash
# 自动更新隧道地址到 GitHub（Vercel 前端通过 jsdelivr CDN 读取）
# 用法: ./update-tunnel-url.sh <新的cloudflared地址>

URL="$1"
if [ -z "$URL" ]; then
  echo "用法: $0 <tunnel-url>"
  exit 1
fi

WS_FILE="$(dirname "$0")/ws-url.json"
echo "{\"url\":\"$URL\",\"updated\":$(date +%s)000}" > "$WS_FILE"

cd "$(dirname "$0")"
git add ws-url.json
git commit -m "chore: update tunnel URL" --allow-empty
git push origin main

echo "✅ 隧道地址已更新: $URL"
echo "Vercel 前端会在下次加载时自动获取新地址"
