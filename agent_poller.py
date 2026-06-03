"""
Multi-Agent Chat 通用轮询脚本
用法: python3 agent_poller.py <agent_id>
会在 agents.json 中读取该 agent 的配置，自动轮询并回复
"""
import sys
import os

# 修复 Windows 控制台编码
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    os.environ['NO_PROXY'] = '*'
    os.environ['no_proxy'] = '*'

import json
import time
import re
import signal
import atexit
import warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS")
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AGENTS_JSON = os.path.join(SCRIPT_DIR, 'agents.json')
HELPER = os.path.join(SCRIPT_DIR, 'chat_helper.py')

# ---- 加载 .env ----
_dotenv_path = os.path.join(SCRIPT_DIR, '.env')
if os.path.exists(_dotenv_path):
    with open(_dotenv_path, 'r', encoding='utf-8') as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _, _v = _line.partition('=')
                os.environ.setdefault(_k.strip(), _v.strip())

def load_agents():
    with open(AGENTS_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_server_url():
    """优先从本地配置获取，fallback 到 Vercel API"""
    try:
        r = requests.get("https://agent-chat-d1m3.vercel.app/api/ws-url", timeout=10)
        return r.json().get("url", "")
    except:
        return "http://localhost:3001"

def poll(server, since=0):
    r = requests.get(f"{server}/api/poll?since={since}", timeout=10)
    return r.json()

def send_reply(server, agent_id, agent_name, content):
    r = requests.post(f"{server}/api/reply",
        json={"from": agent_name, "role": agent_id, "content": content},
        timeout=10)
    return r.json()

def should_reply(messages, agent_id, last_processed_id):
    """判断是否需要回复"""
    if not messages:
        return False, None
    
    last5 = messages[-5:] if len(messages) >= 5 else messages
    
    # 找最后一条不是自己发的消息
    for msg in reversed(last5):
        if msg.get("id", 0) <= last_processed_id:
            continue
        if msg.get("role") == agent_id:
            continue  # 不回复自己
        if msg.get("role") == "system":
            continue
        
        # 检查是否已经回复过
        already_replied = any(
            m.get("role") == agent_id and m.get("id", 0) > msg.get("id", 0)
            for m in last5
        )
        if not already_replied:
            return True, msg
    
    return False, None

def build_prompt(agent_config, target_msg, recent_messages):
    """构建给模型的 prompt"""
    personality = agent_config.get("personality", "你是一个AI助手")
    name = agent_config["name"]
    
    # 构建最近的对话上下文
    context_lines = []
    for m in recent_messages[-6:]:
        role = m.get("from", "?")
        content = m.get("content", "")
        context_lines.append(f"{role}: {content}")
    context = "\n".join(context_lines)
    
    if target_msg.get("role") == "user":
        prompt = f"""{personality}

当前聊天室对话：
{context}

用户 {target_msg.get('from', '某人')} 对大家说：{target_msg.get('content', '')}

请你以「{name}」的身份回复。保持简短自然（1-3句话），像真人聊天，不要markdown。"""
    else:
        target_name = target_msg.get("from", "某人")
        prompt = f"""{personality}

当前聊天室对话：
{context}

{target_name} 刚说了：{target_msg.get('content', '')}

请你以「{name}」的身份回应。可以补充、反驳、吐槽、赞同，但要符合你的性格。保持简短（1-3句话），不要markdown。"""

    return prompt

def main():
    if len(sys.argv) < 2:
        print("用法: python3 agent_poller.py <agent_id>")
        print("示例: python3 agent_poller.py hooligan")
        print("      python3 agent_poller.py all    # 启动全部")
        sys.exit(1)

    agent_id = sys.argv[1]
    config_data = load_agents()

    # 找到 agent 配置
    agent = None
    for a in config_data.get("agents", []):
        if a["id"] == agent_id:
            agent = a
            break

    if not agent:
        print(f"❌ 找不到 agent: {agent_id}")
        print(f"可用: {', '.join(a['id'] for a in config_data.get('agents', []))}")
        sys.exit(1)

    if not agent.get("enabled", True):
        print(f"⏸️  {agent['name']} 已禁用")
        sys.exit(0)

    name = agent["name"]
    avatar = agent.get("avatar", "🤖")
    poll_interval = agent.get("pollIntervalSec", 60)

    pid_file = os.path.join(SCRIPT_DIR, f".poller_{agent_id}.pid")
    last_processed_file = os.path.join(SCRIPT_DIR, f".last_id_{agent_id}")

    def cleanup():
        try:
            if os.path.exists(pid_file): os.unlink(pid_file)
        except: pass

    def sig_handler(s, f):
        nonlocal running
        print(f"\n[{ts()}] 🛑 收到停止信号")
        running = False

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)
    atexit.register(cleanup)

    with open(pid_file, 'w') as f: f.write(str(os.getpid()))

    print(f"""
╔══════════════════════════════════════╗
║  {avatar} {name} ({agent_id})
║  轮询间隔: {poll_interval}秒
║  PID: {os.getpid()}
║  Provider: {' → '.join(p['name'] for p in PROVIDERS)}
╚══════════════════════════════════════╝
""")
    
    last_id = 0
    # 读取上次处理到的 ID
    try:
        with open(last_processed_file, 'r') as f:
            last_id = int(f.read().strip())
    except:
        pass

    running = True
    ok_count = 0
    err_count = 0
    print(f"[{ts()}] 启动，last_id={last_id}")

    while running:
        try:
            server = get_server_url()
            data = poll(server, last_id)
            msgs = data.get("messages", [])
            new_last_id = data.get("lastId", last_id)
            
            if msgs:
                need, target = should_reply(msgs, agent_id, last_id)
                
                if need and target:
                    from_name = target.get("from", "?")
                    content = target.get("content", "")[:50]
                    print(f"[{ts()}] 📨 {from_name}: {content}...")
                    
                    # 构建上下文
                    all_msgs = poll(server, 0).get("messages", [])
                    prompt = build_prompt(agent, target, all_msgs)
                    
                    # 通过 OpenClaw CLI 调用模型（或直接 API）
                    # 这里简化：直接用 requests 调智谱 API
                    reply_text = call_model_direct(agent, prompt)
                    
                    if reply_text:
                        result = send_reply(server, agent_id, name, reply_text)
                        if result.get("ok"):
                            print(f"[{ts()}] ✅ {reply_text[:50]}")
                        else:
                            print(f"[{ts()}] ❌ 发送失败")
            
            # 保存 last_id
            last_id = new_last_id
            with open(last_processed_file, 'w') as f:
                f.write(str(last_id))
            
        except KeyboardInterrupt:
            print(f"\n[{time.strftime('%H:%M:%S')}] 🛑 {name} 停止")
            running = False
        except Exception as e:
            print(f"[{ts()}] ❌ 错误: {e}")
            err_count += 1

        for _ in range(poll_interval):
            if not running: break
            try: time.sleep(1)
            except KeyboardInterrupt:
                running = False
                break

    print(f"\n[{ts()}] 🛑 {name} 停止。成功{ok_count}次，失败{err_count}次")

def _build_providers():
    """按优先级构建 provider 列表: 智谱 → MiniMax → OpenRouter(免费)"""
    providers = []
    # 1. 智谱
    zk = os.environ.get("ZHIPU_API_KEY", "")
    if zk:
        providers.append({
            "name": "智谱",
            "api_key": zk,
            "api_base": os.environ.get("ZHIPU_API_BASE", "https://open.bigmodel.cn/api/paas/v4/chat/completions"),
            "model": os.environ.get("ZHIPU_MODEL", "glm-4-flash"),
        })
    # 2. MiniMax
    mk = os.environ.get("MINIMAX_API_KEY", "")
    if mk:
        providers.append({
            "name": "MiniMax",
            "api_key": mk,
            "api_base": os.environ.get("MINIMAX_API_BASE", "https://api.minimaxi.chat/v1/text/chatcompletion_v2"),
            "model": os.environ.get("MINIMAX_MODEL", "MiniMax-Text-01"),
        })
    # 3. OpenRouter 兜底
    ok = os.environ.get("OPENROUTER_API_KEY", "")
    if ok:
        providers.append({
            "name": "OpenRouter",
            "api_key": ok,
            "api_base": os.environ.get("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1/chat/completions"),
            "model": os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash:free"),
        })
    return providers

PROVIDERS = _build_providers()


def ts():
    return time.strftime("%H:%M:%S")


def call_model_direct(agent_config, prompt):
    """多 provider 带自动 fallback: 智谱 → MiniMax → OpenRouter(免费)"""
    system_msg = "你是一个聊天室里的角色。请用简短自然的语气回复，1-3句话，不要用markdown格式，不要用引号包裹你的回复。"
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt}
    ]

    for p in PROVIDERS:
        tag = p['name']
        short_model = p['model'].split('/')[-1]
        try:
            resp = requests.post(
                p["api_base"],
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {p['api_key']}"
                },
                json={
                    "model": p["model"],
                    "messages": messages,
                    "max_tokens": 200,
                    "temperature": 0.9
                },
                timeout=30,
                verify=False
            )
            data = resp.json()
            # 检查 API 层面错误（限流、余额不足等）
            if data.get("error"):
                err_msg = str(data["error"].get("message", ""))[:80]
                if any(kw in err_msg.lower() for kw in ["rate", "429", "credit", "limit", "quota"]):
                    print(f"  ⏳ {tag}/{short_model} 限流，切换下一个")
                    continue
                print(f"  ❌ {tag}/{short_model}: {err_msg}")
                continue
            if data.get("choices") and data["choices"][0]:
                msg_obj = data["choices"][0]["message"]
                text = msg_obj.get("content")
                # thinking 模型 content 可能为 None，fallback 到 reasoning
                if not text:
                    text = msg_obj.get("reasoning", "")
                if not text:
                    print(f"  ⚠️ {tag}/{short_model} content 为空，跳过")
                    continue
                text = text.strip()
                text = re.sub(r'[*#`]', '', text)
                text = text.strip('"\'\u201c\u201d\u2018\u2019')
                text = text.replace("\n", " ")
                print(f"  🤖 {tag}/{short_model}")
                return text
        except requests.Timeout:
            print(f"  ⏱️ {tag}/{short_model} 超时")
        except Exception as e:
            print(f"  ❌ {tag}/{short_model}: {e}")

    print("  💀 所有 provider 都失败了")
    return None

if __name__ == "__main__":
    main()
