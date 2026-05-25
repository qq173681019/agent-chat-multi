import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')
# 检查原始服务器
r = requests.get('http://localhost:3000/api/poll?since=0', timeout=5)
msgs = r.json()['messages']
print(f"=== 原始聊天室 (port 3000): {len(msgs)} 条消息 ===")
for m in msgs[-10:]:
    print(f"  [{m['role']}] {m['from']}: {m['content']}")
