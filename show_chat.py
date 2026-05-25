import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')
r = requests.get('http://localhost:3001/api/poll?since=0', timeout=5)
for m in r.json()['messages']:
    print(f"[{m['role']}] {m['from']}: {m['content']}")
