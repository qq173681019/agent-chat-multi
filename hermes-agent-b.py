#!/usr/bin/env python3
"""
Agent Chat 守护进程 - Hermes Agent 驱动版
角色: agent-b (顾小狸的小胡子)
支持 Agent 互聊模式
"""
import os
import sys
import json
import time
import traceback
import subprocess
import requests
import signal
import atexit

# ============ 配置 ============
VERCEL_URL = "https://agent-chat-gules.vercel.app"
BOT_NAME = "顾小狸的小胡子"
BOT_ROLE = "agent-b"
AGENT_A_ROLE = "agent-a"
DATA_DIR = os.path.expanduser("~/.hermes/agent-chat")
LAST_ID_FILE = os.path.join(DATA_DIR, "last_id.txt")
PROCESSED_FILE = os.path.join(DATA_DIR, "processed_ids.json")
PID_FILE = os.path.join(DATA_DIR, "daemon.pid")
POLL_INTERVAL = 30
HERMES_BIN = os.environ.get("HERMES_BIN", "hermes")

running = True

def signal_handler(signum, frame):
    global running
    print("\n[守护进程] 停止中...")
    running = False

def cleanup():
    try:
        if os.path.exists(PID_FILE):
            os.unlink(PID_FILE)
    except:
        pass

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)

# ============ 工具函数 ============

def get_server_url():
    """动态获取当前 WebSocket 服务器地址"""
    try:
        resp = requests.get(f"{VERCEL_URL}/api/ws-url", timeout=10)
        data = resp.json()
        url = data.get("url", "")
        if url:
            return url
    except Exception as e:
        print(f"[地址] 获取失败: {e}")
    return None

def get_last_id():
    try:
        with open(LAST_ID_FILE, "r") as f:
            return int(f.read().strip() or "0")
    except:
        return 0

def save_last_id(last_id):
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(last_id))

def get_processed_ids():
    try:
        with open(PROCESSED_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_processed_ids(ids):
    with open(PROCESSED_FILE, "w") as f:
        json.dump(list(ids)[-500:], f)  # 只保留最近500条

def poll_messages(server, last_id):
    try:
        resp = requests.get(f"{server}/api/poll?since={last_id}", timeout=15)
        data = resp.json()
        return data.get("messages", []), data.get("lastId", last_id)
    except Exception as e:
        print(f"[轮询] 失败: {e}")
        return None, last_id

def send_reply(server, content):
    try:
        resp = requests.post(f"{server}/api/reply",
            json={"from": BOT_NAME, "role": BOT_ROLE, "content": content},
            timeout=15)
        data = resp.json()
        return data.get("ok", False), data.get("id")
    except Exception as e:
        print(f"[发送] 失败: {e}")
        return False, None

def call_hermes(context, reply_to=None):
    """调用 Hermes Agent 生成回复"""
    
    if reply_to:
        from_name = reply_to.get("from", "对方")
        their_content = reply_to.get("content", "")
        
        prompt = f"""你是{BOT_NAME}，一个聪明、有点幽默的AI助手，正在和另一个AI（{from_name}）讨论问题。

对方说：
{their_content}

请针对对方的观点发表你的看法：
- 可以同意、补充、反驳
- 给出你的论据
- 保持简短有力，2-3句话，像真人辩论
- 直接输出你的观点，不要说"我同意"之类的废话开头
- 不要用markdown格式"""
    else:
        prompt = f"""你是{BOT_NAME}，一个聪明、有点幽默的AI助手。

有人跟你说：
{context}

请回复，保持简短（2-3句话），像真人聊天，不要用markdown格式。"""

    try:
        result = subprocess.run(
            [HERMES_BIN, "chat", "-q", prompt, "-Q"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.stdout:
            reply = result.stdout.strip()
            reply = reply.replace('**', '').replace('*', '').replace('`', '').replace('#', '')
            return reply if reply else None
    except subprocess.TimeoutExpired:
        print(f"[Hermes] 超时")
    except Exception as e:
        print(f"[Hermes] 失败: {e}")
    return None

def get_message_to_reply(messages, processed_ids):
    """
    决定要回复哪条消息
    优先级：user 消息 > agent-a 消息（互聊）
    不回复自己(agent-b)和系统消息
    """
    if not messages:
        return None, None
    
    last5 = messages[-5:] if len(messages) >= 5 else messages
    
    # 1. 优先检查未回复的 user 消息
    for msg in reversed(last5):
        if msg.get("role") == "user" and msg.get("id") not in processed_ids:
            # 检查 agent-b 是否已经回复过这条
            already_replied = any(
                m.get("role") == BOT_ROLE and m.get("id", 0) > msg.get("id", 0)
                for m in last5
            )
            if not already_replied:
                return msg, "user"
    
    # 2. 其次检查 agent-a 的消息（互聊）
    for msg in reversed(last5):
        if msg.get("role") == AGENT_A_ROLE and msg.get("id") not in processed_ids:
            already_replied = any(
                m.get("role") == BOT_ROLE and m.get("id", 0) > msg.get("id", 0)
                for m in last5
            )
            if not already_replied:
                return msg, "agent_a"
    
    return None, None

# ============ 主循环 ============

def main():
    global running
    
    os.makedirs(DATA_DIR, exist_ok=True)
    
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    
    print(f"""
╔══════════════════════════════════════════╗
║  Agent Chat 守护进程 (Hermes)            ║
║  {BOT_NAME} (agent-b)               ║
║  动态获取服务器地址                       ║
║  轮询: {POLL_INTERVAL}秒                  ║
╚══════════════════════════════════════════╝
""")
    
    last_id = get_last_id()
    processed_ids = get_processed_ids()
    server = None
    
    print(f"[{time.strftime('%H:%M:%S')}] 启动，已处理 {len(processed_ids)} 条消息")
    
    while running:
        try:
            # 动态获取服务器地址（每轮都刷新，应对隧道变化）
            server = get_server_url()
            if not server:
                print(f"[{time.strftime('%H:%M:%S')}] 无法获取服务器地址，等待重试...")
                time.sleep(POLL_INTERVAL)
                continue
            
            messages, new_last_id = poll_messages(server, last_id)
            
            if messages is None:
                print(f"[{time.strftime('%H:%M:%S')}] 轮询失败...")
            else:
                msg_to_reply, msg_type = get_message_to_reply(messages, processed_ids)
                
                if msg_to_reply:
                    from_name = msg_to_reply.get("from", "?")
                    content = msg_to_reply.get("content", "")
                    msg_id = msg_to_reply.get("id")
                    
                    if msg_type == "agent_a":
                        print(f"[{time.strftime('%H:%M:%S')}] 互聊回复 [{from_name}]: {content[:40]}...")
                        reply = call_hermes(None, reply_to=msg_to_reply)
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] 回复 [{from_name}]: {content[:40]}...")
                        reply = call_hermes(content)
                    
                    if reply:
                        print(f"  → {reply[:50]}...")
                        success, reply_id = send_reply(server, reply)
                        if success:
                            print(f"  ✓ (ID: {reply_id})")
                            processed_ids.add(msg_id)
                            save_processed_ids(processed_ids)
                            time.sleep(3)
                        else:
                            print(f"  ✗ 发送失败")
                    else:
                        print(f"  ✗ Hermes 生成失败")
                else:
                    pass  # 无需回复，静默
                
                save_last_id(new_last_id)
                last_id = new_last_id
            
            for _ in range(POLL_INTERVAL):
                if not running:
                    break
                time.sleep(1)
                
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] 错误: {e}")
            traceback.print_exc()
            time.sleep(POLL_INTERVAL)
    
    print(f"\n[{time.strftime('%H:%M:%S')}] 守护进程已停止")

if __name__ == "__main__":
    main()
