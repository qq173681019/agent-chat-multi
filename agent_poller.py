"""
Multi-Agent Chat 通用轮询脚本
用法: python3 agent_poller.py <agent_id>
会在 agents.json 中读取该 agent 的配置，自动轮询并回复
"""
import sys
import os

# 修复 Windows 控制台编码
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
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

# ---- 全局暂停密令(用户说"停止对话" → 5 个 bot 全部静默) ----
# 暂停状态持久化:存在 .paused = 暂停,不存在 = 运行
PAUSE_FILE = os.path.join(SCRIPT_DIR, '.paused')
# 密令匹配:停止(可加对话/吧/了/一下/说话)/ 恢复对话(可加开始说话/继续说话/说吧)
STOP_COMMAND_RE = re.compile(r"^\s*停止\s*(?:对话|吧|了|一下|说话)?\s*[。!！~～]?\s*$")
RESUME_COMMAND_RE = re.compile(r"^\s*(?:恢复对话|开始说话|继续说话|继续吧|说吧|恢复吧)\s*[。!！~～]?\s*$")

# 机器人 ID 集合(在模块加载时从 agents.json 读一次)
# 用途: 判断一条消息是用户发的还是 bot 发的(role 字段 chat server 会重写为发送者 ID)
_BOT_IDS = set()
def _refresh_bot_ids():
    """每次从 agents.json 重读 bot id 集合(支持运行时新增/删除 agent)"""
    try:
        with open(AGENTS_JSON, 'r', encoding='utf-8') as _f:
            cfg = json.load(_f)
        return {a.get("id") for a in cfg.get("agents", []) if a.get("id")}
    except Exception:
        return set()

def is_user_message(msg):
    """判断一条消息是不是用户发的(非任何 bot)"""
    role = msg.get("role", "")
    if not _BOT_IDS:
        # 懒加载
        _BOT_IDS.update(_refresh_bot_ids())
    # 角色不在 bot 列表里 → 是用户
    if role not in _BOT_IDS:
        return True
    return False

def is_stop_command(text):
    return bool(text) and bool(STOP_COMMAND_RE.match(text.strip()))

def is_resume_command(text):
    return bool(text) and bool(RESUME_COMMAND_RE.match(text.strip()))

def set_paused(paused: bool, who: str = ""):
    """创建/删除 .paused 文件。who 是触发该动作的 bot 名,用于日志。"""
    if paused:
        if not os.path.exists(PAUSE_FILE):
            with open(PAUSE_FILE, 'w', encoding='utf-8') as f:
                f.write(f"paused by {who} at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            print(f"[{ts()}] ⏸️  全局暂停已启用 (by {who})")
    else:
        if os.path.exists(PAUSE_FILE):
            os.remove(PAUSE_FILE)
            print(f"[{ts()}] ▶️  全局暂停已解除 (by {who})")

# ---- 加载 .env ----
# 优先级: 项目 .env(显式覆盖) > ~/.hermes/.env(共享密钥)
# 注意: poller 可能在 Windows python 跑(~=C:\Users\admin),
#       也可能在 WSL python 跑(~=/home/jerico)。两个都尝试。
_HERMES_HOME_CANDIDATES = [
    os.path.expanduser('~/.hermes/.env'),             # 当前 OS 用户家目录
    r'C:\Users\admin\.hermes\.env',                    # Windows 硬编码(原生 Windows python)
    r'\\wsl$\Ubuntu\home\jerico\.hermes\.env',         # 从 Windows 访问 WSL 的 jerico 用户
    '/mnt/c/Users/admin/.hermes/.env',                 # WSL 视角下的 Windows 用户目录
    '/home/jerico/.hermes/.env',                       # WSL 直接路径
]
_extra_env_paths = [os.path.join(SCRIPT_DIR, '.env')]   # 项目本地覆盖(优先)
for _hp in _HERMES_HOME_CANDIDATES:
    if os.path.exists(_hp):
        _extra_env_paths.append(_hp)
for _env_path in _extra_env_paths:
    if not os.path.exists(_env_path):
        continue
    with open(_env_path, 'r', encoding='utf-8') as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _, _v = _line.partition('=')
                # 跳过空值占位符(如 "sk-cp-…Sd7g" 这种脱敏串)
                if '…' in _v or '...' in _v:
                    continue
                os.environ.setdefault(_k.strip(), _v.strip())

def load_agents():
    with open(AGENTS_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)

# 服务器地址：固定走 multi.agent-chat.org（独立仓库，独立隧道）
# 不再依赖 Vercel 动态地址（Vercel 是老主干 agent-chat 的部署，已废弃）
SERVER_URL = os.environ.get("CHAT_SERVER_URL", "https://multi.agent-chat.org")

def get_server_url():
    """固定地址: https://multi.agent-chat.org"""
    return SERVER_URL

def poll(since=0):
    """轮询消息（不带 server 参数，固定用 SERVER_URL）"""
    r = requests.get(f"{SERVER_URL}/api/poll?since={since}", timeout=10, verify=False)
    return r.json()

def send_reply(agent_id, agent_name, content):
    """发送回复（不带 server 参数，固定用 SERVER_URL）"""
    r = requests.post(f"{SERVER_URL}/api/reply",
        json={"from": agent_name, "role": agent_id, "content": content},
        timeout=10, verify=False)
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
            data = poll(last_id)
            msgs = data.get("messages", [])
            new_last_id = data.get("lastId", last_id)

            # ---- 全局暂停检查: 看到 .paused 文件就跳过本轮 LLM ----
            # 但仍然要检测用户发的"恢复对话"密令(否则会死锁)
            if os.path.exists(PAUSE_FILE):
                resume_target = None
                if msgs:
                    # 只看"不是自己"的消息(should_reply 帮我们过滤)
                    for m in msgs:
                        if m.get("id", 0) <= last_id:
                            continue
                        if m.get("role") == agent_id:
                            continue
                        if is_resume_command(m.get("content", "")):
                            resume_target = m
                            break
                if resume_target:
                    # 触发恢复
                    set_paused(False, who=name)
                    ack = f"▶️ 收到「恢复对话」,所有 bot 重新上线。"
                    send_reply(agent_id, name, ack)
                    print(f"[{ts()}] ▶️  密令已确认: 恢复对话(从 paused 分支)")
                    new_last_id = max(new_last_id, resume_target.get("id", new_last_id))
                    last_id = new_last_id
                    with open(last_processed_file, 'w') as f:
                        f.write(str(last_id))
                    continue
                # 没看到恢复密令 → 纯静默,睡到下一轮
                last_id = new_last_id
                with open(last_processed_file, 'w') as f:
                    f.write(str(last_id))
                for _ in range(poll_interval):
                    if not running: break
                    try: time.sleep(1)
                    except KeyboardInterrupt:
                        running = False
                        break
                continue

            if msgs:
                need, target = should_reply(msgs, agent_id, last_id)

                if need and target:
                    from_name = target.get("from", "?")
                    content = target.get("content", "")[:50]
                    print(f"[{ts()}] 📨 {from_name}: {content}...")

                    # ---- 密令检测(必须在 topic 门控之前,优先级最高) ----
                    # 设计: chat server 不会传"用户"专属 role,所有消息的 role 都是发送者 ID
                    # (用户用 guxiaolang/guxiaoli 登录,role 也是这个)
                    # 所以这里不限制 role,只让 should_reply 排除自己(已做)
                    # 这样设计的好处: 即便用户用 guxiaolang 账号发的"停止对话"也能触发
                    target_text = target.get("content", "")
                    if is_stop_command(target_text):
                        # 1. 创建 .paused 标志
                        set_paused(True, who=name)
                        # 2. 发一条固定确认(走系统级固定文本,不走 LLM,省 token)
                        ack = f"⏸️ 收到「停止对话」,所有 bot 静默。说「恢复对话」可重新开启。"
                        send_reply(agent_id, name, ack)
                        print(f"[{ts()}] ⏸️  密令已确认: 停止对话")
                        new_last_id = max(new_last_id, target.get("id", new_last_id))
                        last_id = new_last_id
                        with open(last_processed_file, 'w') as f:
                            f.write(str(last_id))
                        continue
                    if is_resume_command(target_text):
                        set_paused(False, who=name)
                        ack = f"▶️ 收到「恢复对话」,所有 bot 重新上线。"
                        send_reply(agent_id, name, ack)
                        print(f"[{ts()}] ▶️  密令已确认: 恢复对话")
                        new_last_id = max(new_last_id, target.get("id", new_last_id))
                        last_id = new_last_id
                        with open(last_processed_file, 'w') as f:
                            f.write(str(last_id))
                        continue

                    # 话题门控: 如果 agent 配置了 triggerMode=finance_only,
                    # 先用 david_agent 的关键词判定,无关话题直接静默
                    trigger_mode = agent.get("triggerMode", "always")
                    david_mod = None
                    if trigger_mode == "finance_only":
                        try:
                            import david_agent as david_mod
                        except Exception as _e:
                            print(f"  ⚠️ david_agent 加载失败,降级为普通回复: {_e}")
                            trigger_mode = "always"
                    if trigger_mode == "finance_only" and david_mod is not None:
                        relevant = david_mod.topic_relevant(target.get("content", ""))
                        if not relevant:
                            # 用最后 5 条消息做一次兜底: 如果最近几条里有任意一条沾金融,
                            # 也算"上下文相关",允许 David 插话(避免被忽略太死)
                            ctx_relevant = any(
                                david_mod.topic_relevant(m.get("content", ""))
                                for m in msgs[-5:]
                                if m.get("role") != "system" and m.get("role") != agent_id
                            )
                            if not ctx_relevant:
                                print(f"  🔇 [topic] 静默:与金融无关,David 不插话")
                                # 仍然推进 last_id,避免下一轮重复看到
                                new_last_id = max(new_last_id, target.get("id", new_last_id))
                                last_id = new_last_id
                                with open(last_processed_file, 'w') as f:
                                    f.write(str(last_id))
                                continue

                    # 构建上下文
                    all_msgs = poll(0).get("messages", [])
                    prompt = build_prompt(agent, target, all_msgs)

                    # 调用 LLM(默认路径 / David 路径)
                    if trigger_mode == "finance_only" and david_mod is not None:
                        try:
                            reply_text = david_mod.run_david(
                                sys.modules[__name__], agent, target, all_msgs
                            )
                            if reply_text is None:
                                print(f"  🔇 [david] 跑完无文本,跳过")
                        except Exception as e:
                            print(f"  ❌ [david] 异常,降级为普通路径: {e}")
                            reply_text = call_model_direct(agent, prompt)
                    else:
                        reply_text = call_model_direct(agent, prompt)

                    if reply_text:
                        result = send_reply(agent_id, name, reply_text)
                        if result.get("ok"):
                            print(f"[{ts()}] ✅ {reply_text[:50]}")
                        else:
                            print(f"[{ts()}] ❌ 发送失败")

                        # 回复后重新 poll 拿最新 last_id（因为 send_reply 会增加消息 ID）
                        latest = poll(last_id)
                        new_last_id = latest.get("lastId", new_last_id)
            
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

# ---- 协议标记:provider 走 openai-chat 还是 anthropic-messages ----
# openai-chat:  POST {api_base}   body={model, messages:[{role, content}], max_tokens, temperature}
#               response.choices[0].message.content
# anthropic:    POST {api_base}/v1/messages   body={model, system, messages, max_tokens}
#               response.content[i].text  (可能夹杂 thinking 块)
OPENAI_CHAT = "openai_chat"
ANTHROPIC_MSGS = "anthropic_msgs"

def _build_providers():
    """按优先级构建 provider 列表:
       minimax-cn(MiniMax-M3,国内) → 智谱 → OpenRouter(免费)
       minimax-cn 走 Anthropic Messages 协议(api.minimaxi.com/anthropic,Bearer auth)
    """
    providers = []
    # 1. minimax-cn(MiniMax-M3,主用)
    mk_cn = os.environ.get("MINIMAX_CN_API_KEY", "")
    if mk_cn:
        providers.append({
            "name": "MiniMax-cn",
            "api_key": mk_cn,
            "api_base": os.environ.get("MINIMAX_CN_API_BASE", "https://api.minimaxi.com/anthropic"),
            "model": os.environ.get("MINIMAX_CN_MODEL", "MiniMax-M3"),
            "protocol": ANTHROPIC_MSGS,
        })
    # 2. 智谱(兜底 1)
    zk = os.environ.get("ZHIPU_API_KEY", "")
    if zk:
        providers.append({
            "name": "智谱",
            "api_key": zk,
            "api_base": os.environ.get("ZHIPU_API_BASE", "https://open.bigmodel.cn/api/paas/v4/chat/completions"),
            "model": os.environ.get("ZHIPU_MODEL", "glm-4-flash"),
            "protocol": OPENAI_CHAT,
        })
    # 3. OpenRouter 兜底
    ok = os.environ.get("OPENROUTER_API_KEY", "")
    if ok:
        providers.append({
            "name": "OpenRouter",
            "api_key": ok,
            "api_base": os.environ.get("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1/chat/completions"),
            "model": os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash:free"),
            "protocol": OPENAI_CHAT,
        })
    return providers

PROVIDERS = _build_providers()


def ts():
    return time.strftime("%H:%M:%S")


def _extract_anthropic_text(data):
    """从 Anthropic Messages 响应里抽 text,跳过 thinking 块"""
    content = data.get("content") or []
    parts = []
    for blk in content:
        if not isinstance(blk, dict):
            continue
        btype = blk.get("type")
        if btype == "text":
            t = blk.get("text", "")
            if t:
                parts.append(t)
    return "\n".join(parts).strip()


def _call_openai_chat(p, messages, max_tokens):
    """OpenAI 兼容 chat completions"""
    resp = requests.post(
        p["api_base"],
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {p['api_key']}"
        },
        json={
            "model": p["model"],
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.9
        },
        timeout=30,
        verify=False
    )
    return resp.json()


def _call_anthropic_msgs(p, system_msg, user_msg, max_tokens):
    """Anthropic Messages API(兼容层,MiniMax 国内端走这个)"""
    url = p["api_base"].rstrip("/") + "/v1/messages"
    resp = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {p['api_key']}",
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": p["model"],
            "system": system_msg,
            "messages": [{"role": "user", "content": user_msg}],
            "max_tokens": max_tokens,
            "temperature": 0.9,
        },
        timeout=30,
        verify=False
    )
    return resp.json()


def call_model_direct(agent_config, prompt):
    """多 provider 带自动 fallback: minimax-cn → 智谱 → OpenRouter(免费)"""
    system_msg = "你是一个聊天室里的角色。请用简短自然的语气回复，1-3句话，不要用markdown格式，不要用引号包裹你的回复。"

    for p in PROVIDERS:
        tag = p['name']
        short_model = p['model'].split('/')[-1]
        protocol = p.get("protocol", OPENAI_CHAT)
        try:
            if protocol == ANTHROPIC_MSGS:
                data = _call_anthropic_msgs(p, system_msg, prompt, max_tokens=200)
            else:
                messages = [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt}
                ]
                data = _call_openai_chat(p, messages, max_tokens=200)

            # 错误检测
            if data.get("error"):
                err_msg = str(data["error"].get("message", ""))[:80]
                if any(kw in err_msg.lower() for kw in ["rate", "429", "credit", "limit", "quota"]):
                    print(f"  ⏳ {tag}/{short_model} 限流，切换下一个")
                    continue
                print(f"  ❌ {tag}/{short_model}: {err_msg}")
                continue

            # 解析响应
            if protocol == ANTHROPIC_MSGS:
                text = _extract_anthropic_text(data)
                err_type = data.get("type") == "error"
                if err_type:
                    err = data.get("error", {})
                    print(f"  ❌ {tag}/{short_model}: {err.get('type','')} {str(err.get('message',''))[:60]}")
                    continue
            else:
                if not (data.get("choices") and data["choices"][0]):
                    print(f"  ⚠️ {tag}/{short_model} 无 choices，跳过")
                    continue
                msg_obj = data["choices"][0]["message"]
                text = msg_obj.get("content")
                if not text:
                    text = msg_obj.get("reasoning", "")
                if not text:
                    print(f"  ⚠️ {tag}/{short_model} content 为空，跳过")
                    continue

            text = text.strip()
            if not text:
                print(f"  ⚠️ {tag}/{short_model} 抽不到 text，跳过")
                continue
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
