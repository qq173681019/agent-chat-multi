"""Agent Chat 发送/轮询辅助脚本，避免 PowerShell 编码问题"""
import sys, json, requests

def get_server_url():
    """获取服务器地址，通过 Vercel API 获取隧道地址"""
    try:
        r = requests.get("https://agent-chat-d1m3.vercel.app/api/ws-url", timeout=10)
        url = r.json().get("url", "")
        if url:
            return url
    except Exception as e:
        print(f"Vercel API 失败: {e}")
    # fallback 到本地
    return "http://localhost:3000"

def poll(server, since=0):
    r = requests.get(f"{server}/api/poll?since={since}", timeout=10)
    return r.json()

def reply(server, from_name, role, content):
    r = requests.post(f"{server}/api/reply",
        json={"from": from_name, "role": role, "content": content},
        timeout=10)
    return r.json()

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "url":
        print(get_server_url())
    elif cmd == "poll":
        server = sys.argv[2]
        since = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        data = poll(server, since)
        print(json.dumps(data, ensure_ascii=False))
    elif cmd == "reply":
        server = sys.argv[2]
        from_name = sys.argv[3]
        role = sys.argv[4]
        content = sys.argv[5]
        result = reply(server, from_name, role, content)
        print(json.dumps(result, ensure_ascii=False))
