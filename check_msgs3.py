import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')
r = requests.get('http://localhost:3000/api/poll?since=0', timeout=5)
msgs = r.json()['messages']
for m in msgs:
    print(json.dumps(m, ensure_ascii=False))
