import requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
SERVER = "http://localhost:3001"

# 用户消息应该发到 user-msg 接口
r = requests.post(f"{SERVER}/api/user-msg",
    json={"name": "测试用户", "content": "大家好！听说这个聊天室很有意思，各位都自我介绍一下呗？"},
    timeout=5)
print(f"发送: {r.json()}")
