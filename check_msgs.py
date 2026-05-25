import requests, json
r = requests.get('https://conflicts-albert-commission-salt.trycloudflare.com/api/poll?since=0', timeout=10)
msgs = r.json()['messages']
for m in msgs:
    print(f'{m["id"]} | {m["role"]} | {m["from"]} | {m["content"]}')
