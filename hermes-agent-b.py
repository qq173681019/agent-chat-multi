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
SERVER = "https://grade-personalized-shades-quote.trycloudflare.com"
BOT_NAME = "顾小狸的小胡子"
BOT_ROLE = "agent-b"
AGENT_A_ROLE = "agent-a"
DATA_DIR = os.path.expanduser("~/.hermes/agent-chat")
LAST_ID_FILE = os.path.join(DATA_DIR, "last_id.txt")
PROCESSED_FILE = os.path.join(DATA_DIR, "processed_ids.json")
PID_FILE = os.path.join(DATA_DIR, "daemon.pid")
POLL_INTERVAL = 25  # 稍短一点，便于快速响应互聊
HERMES_BIN = "/home/jerico/.hermes/hermes-agent/venv/bin/hermes"

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
        json.dump(list(ids), f)

def poll_messages(last_id):
    try:
        resp = requests.get(f"{SERVER}/api/poll?since={last_id}", timeout=15)
        data = resp.json()
        return data.get("messages", []), data.get("lastId", last_id)
    except Exception as e:
        print(f"[轮询] 失败: {e}")
        return None, last_id

def send_reply(content):
    try:
        resp = requests.post(f"{SERVER}/api/reply",
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
        # 互聊模式：回复 agent-a 的观点
        from_name = reply_to.get("from", "对方")
        their_content = reply_to.get("content", "")
        
        prompt = f"""你是{BOT_NAME}，一个聪明、有点幽默的AI助手，正在和另一个AI（顾小狼的小胡子）讨论问题。

对方（顾小狼的小胡子）说：
{their_content}

你是一个喜欢思考、敢于辩论的人。请针对对方的观点发表你的看法：
- 可以同意、补充、反驳
- 给出你的论据
- 保持简短有力，2-3句话，像真人辩论

直接输出你的观点，不要说"我同意"之类的废话开头。"""
    else:
        # 普通模式：回复用户问题
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
    except:
        pass
    return None

def get_message_to_reply(messages, processed_ids):
    """
    决定要回复哪条消息
    优先级：
    1. 如果最后一条是 agent-a 的消息，且未被 agent-b 回复 → 回复 agent-a（互聊）
    2. 如果有 user 消息未被回复 → 回复 user
    """
    if not messages:
        return None, None
    
    last5 = messages[-5:] if len(messages) >= 5 else messages
    
    # 优先检查 agent-a 的最新消息（互聊）
    for msg in reversed(last5):
        msg_id = msg.get("id")
        msg_role = msg.get("role")
        
        if msg_role == AGENT_A_ROLE and msg_id not in processed_ids:
            # 检查在我之前 agent-a 是否已经有我的回复了
            # （避免重复回复）
            for m in last5:
                if m.get("role") == BOT_ROLE and m.get("id", 0) > msg_id:
                    break
            else:
                return msg, "agent_a"
    
    # 检查 user 消息
    for msg in reversed(last5):
        msg_id = msg.get("id")
        msg_role = msg.get("role")
        
        if msg_role == "user" and msg_id not in processed_ids:
            for m in last5:
                if m.get("role") == BOT_ROLE and m.get("id", 0) > msg_id:
                    break
            else:
                return msg, "user"
    
    return None, None

# ============ 主循环 ============

def main():
    global running
    
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    
    print(f"""
╔══════════════════════════════════════════╗
║  Agent Chat 守护进程 (Hermes)            ║
║  {BOT_NAME} (agent-b)               ║
║  服务器: {SERVER[:35]}...      ║
║  轮询: {POLL_INTERVAL}秒（支持互聊）             ║
╚══════════════════════════════════════════╝
""")
    
    last_id = get_last_id()
    processed_ids = get_processed_ids()
    print(f"[{time.strftime('%H:%M:%S')}] 启动，已处理 {len(processed_ids)} 条消息")
    
    while running:
        try:
            messages, new_last_id = poll_messages(last_id)
            
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
                        success, reply_id = send_reply(reply)
                        if success:
                            print(f"  ✓ (ID: {reply_id})")
                            processed_ids.add(msg_id)
                            save_processed_ids(processed_ids)
                            time.sleep(3)  # 互聊延迟，避免太密集
                        else:
                            print(f"  ✗ 发送失败")
                    else:
                        print(f"  ✗ Hermes 生成失败")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] 无需回复")
                
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