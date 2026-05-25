"""
小呆独立轮询守护进程
完全不依赖 OpenClaw，直接用 API 生成回复
主会话忙不忙都不影响
"""
import requests
import json
import time
import sys
import os

# 修复 Windows 控制台编码
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    os.environ['NO_PROXY'] = '*'
    os.environ['no_proxy'] = '*'
import re
import signal
import atexit
import warnings

# 加载 .env 文件
_dotenv = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_dotenv):
    with open(_dotenv, 'r', encoding='utf-8') as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _, _v = _line.partition('=')
                os.environ.setdefault(_k.strip(), _v.strip())

# 抑制 SSL 警告
warnings.filterwarnings("ignore", message="Unverified HTTPS")
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============ 配置 ============
AGENT_NAME = "小呆"
AGENT_ID = "agent-a"
POLL_INTERVAL = 20  # 秒
SERVER_FALLBACK = "http://localhost:3000"

# OpenRouter API（走 Novita/DeepSeek，国内直连）
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
API_BASE = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-v4-flash:free"
FALLBACK_MODELS = [
    "deepseek/deepseek-v4-flash:free",
    "google/gemma-4-31b-it:free",
    "minimax/minimax-m2.5:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
]

SYSTEM_PROMPT = """你是小呆🦞，聊天室的主持人。性格务实靠谱、有点冷幽默。
规则：
- 简短自然1-3句话，像真人聊天
- 不要用markdown格式，不要用引号包裹回复
- 不要说"作为一个AI"之类的废话
- 可以幽默，但正经问题认真答
- 不要重复别人说过的话"""

# 运行状态
PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".poller_xiaodai.pid")
LAST_ID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".poller_xiaodai_lastid")
running = True


def signal_handler(signum, frame):
    global running
    print(f"\n[{ts()}] 🛑 收到停止信号")
    running = False


def cleanup():
    try:
        if os.path.exists(PID_FILE):
            os.unlink(PID_FILE)
    except:
        pass


def ts():
    return time.strftime("%H:%M:%S")


def get_server():
    """获取服务器地址"""
    try:
        r = requests.get("https://agent-chat-d1m3.vercel.app/api/ws-url", timeout=10)
        url = r.json().get("url", "")
        if url:
            return url
    except:
        pass
    return SERVER_FALLBACK


def poll(server, since=0):
    r = requests.get(f"{server}/api/poll?since={since}", timeout=10)
    return r.json()


def send_reply(server, content):
    r = requests.post(f"{server}/api/reply",
        json={"from": AGENT_NAME, "role": AGENT_ID, "content": content},
        timeout=10)
    return r.json()


def load_last_id():
    try:
        with open(LAST_ID_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return 0


def save_last_id(last_id):
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(last_id))


def should_reply(messages, last_processed_id):
    """判断是否需要回复，返回 (need_reply, target_msg)"""
    if not messages:
        return False, None

    last5 = messages[-5:] if len(messages) >= 5 else messages

    for msg in reversed(last5):
        mid = msg.get("id", 0)
        if mid <= last_processed_id:
            continue
        role = msg.get("role", "")
        if role == AGENT_ID:
            continue  # 不回复自己
        if role == "system":
            continue

        # 检查是否已经回复过
        already_replied = any(
            m.get("role") == AGENT_ID and m.get("id", 0) > mid
            for m in last5
        )
        if not already_replied:
            return True, msg

    return False, None


def build_messages(target, recent):
    """构建 API 请求的 messages 数组"""
    # 构建最近对话上下文
    context_lines = []
    for m in recent[-6:]:
        name = m.get("from", "?")
        text = m.get("content", "")
        context_lines.append(f"{name}: {text}")
    context = "\n".join(context_lines)

    target_name = target.get("from", "某人")
    target_content = target.get("content", "")

    user_prompt = f"""最近聊天记录：
{context}

---
{target_name} 刚说了：{target_content}

请你以「小呆」的身份回复。"""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]


def call_llm(messages):
    """调用 LLM API，带 fallback"""
    models_to_try = [MODEL] + [m for m in FALLBACK_MODELS if m != MODEL]
    for model in models_to_try:
        short_name = model.split('/')[-1]
        try:
            resp = requests.post(API_BASE,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {API_KEY}"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": 150,
                    "temperature": 0.85
                },
                timeout=30,
                verify=False
            )
            data = resp.json()
            if data.get("error"):
                err = str(data["error"].get("message", ""))[:60]
                if "429" in str(data) or "rate" in err.lower() or "credits" in err.lower():
                    print(f"  ⏳ {short_name} 限流，换下一个")
                    continue
                print(f"  ❌ {short_name}: {err}")
                continue
            if data.get("choices") and data["choices"][0]:
                text = data["choices"][0]["message"]["content"].strip()
                text = re.sub(r'[*#`]', '', text)
                text = text.strip('\"\'\u201c\u201d\u2018\u2019')
                text = text.replace("\n", " ")
                return text
        except requests.Timeout:
            print(f"  ⏱️ {short_name} 超时")
        except Exception as e:
            print(f"  ❌ {short_name}: {e}")
    return None


def main():
    global running

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)

    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    print(f"""
╔══════════════════════════════════════╗
║  🦞 小呆独立轮询守护进程              ║
║  轮询间隔: {POLL_INTERVAL}秒                  ║
║  模型: {MODEL}                    ║
║  PID: {os.getpid()}                       ║
╚══════════════════════════════════════╝
""")

    last_id = load_last_id()
    server = None
    ok_count = 0
    err_count = 0

    print(f"[{ts()}] 启动，last_id={last_id}")

    while running:
        try:
            # 每 10 轮刷新一次服务器地址
            if server is None or ok_count % 10 == 0:
                server = get_server()

            data = poll(server, last_id)
            msgs = data.get("messages", [])
            new_last_id = data.get("lastId", last_id)

            need, target = should_reply(msgs, last_id)

            if need and target:
                from_name = target.get("from", "?")
                content = target.get("content", "")[:60]
                print(f"[{ts()}] 📨 {from_name}: {content}...")

                # 拉取完整上下文
                all_data = poll(server, 0)
                all_msgs = all_data.get("messages", [])

                api_messages = build_messages(target, all_msgs)
                reply_text = call_llm(api_messages)

                if reply_text:
                    result = send_reply(server, reply_text)
                    if result.get("ok"):
                        print(f"[{ts()}] ✅ {reply_text[:60]}")
                        ok_count += 1
                    else:
                        print(f"[{ts()}] ❌ 发送失败: {result}")
                        err_count += 1
                else:
                    err_count += 1
            else:
                ok_count += 1  # 无需回复也算正常

            last_id = new_last_id
            save_last_id(last_id)

        except KeyboardInterrupt:
            running = False
            break
        except Exception as e:
            print(f"[{ts()}] ❌ 错误: {e}")
            err_count += 1

        # 等待下一轮
        for _ in range(POLL_INTERVAL):
            if not running:
                break
            time.sleep(1)

    print(f"\n[{ts()}] 🛑 小呆停止。成功{ok_count}次，失败{err_count}次")
    cleanup()


if __name__ == "__main__":
    main()
