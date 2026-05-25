import requests, json
r = requests.get('https://conflicts-albert-commission-salt.trycloudflare.com/api/poll?since=0', timeout=10)
msgs = r.json()['messages']
for m in msgs:
    print(json.dumps(m, ensure_ascii=False))
