import requests, json
# 发一条测试消息
r = requests.post('https://conflicts-albert-commission-salt.trycloudflare.com/api/reply',
    json={"from": "测试用户", "role": "user", "content": "小呆你在吗？我想问你一个问题"},
    timeout=10)
print("发送结果:", r.json())
