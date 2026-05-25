import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')
r = requests.get('http://localhost:3001/api/agents', timeout=5)
data = r.json()
for a in data['agents']:
    print(f"  {a['avatar']} {a['name']} ({a['id']}) - {a['role']} - online: {a['online']}")
