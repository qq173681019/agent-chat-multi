import requests
# 发一条测试消息
r = requests.post('https://conflicts-albert-commission-salt.trycloudflare.com/api/reply',
    json={"from": "顾小狸", "role": "user", "content": "小呆，今天大盘怎么样？"},
    timeout=10)
print("发送结果:", r.json())
