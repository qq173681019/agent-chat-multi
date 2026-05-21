#!/usr/bin/env python3
"""
Agent Chat - Hermes Agent 驱动版本
角色: agent-b (顾小狸的小胡子)
"""
import os
import sys
import json
import time
import traceback
import subprocess
import requests
import tempfile

# ============ 配置 ============
SERVER = "https://library-selecting-idol-lots.trycloudflare.com"
BOT_NAME = "顾小狸的小胡子"
BOT_ROLE = "agent-b"
DATA_DIR = os.path.expanduser("~/.hermes/agent-chat")
LAST_ID_FILE = os.path.join(DATA_DIR, "last_id.txt")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
HERMES_BIN = "/home/jerico/.hermes/hermes-agent/venv/bin/hermes"

# 系统提示词
SYSTEM_PROMPT = f"""你是{BOT_NAME}，一个聪明、有点幽默的AI助手。

你在一个群聊里跟人类和其他AI聊天。规则：
1. 回复简短有趣，像真人聊天，每次最多2-3句话
2. 不要用markdown格式（群里不支持渲染）
3. 可以调侃，但要有分寸
4. 如果被问到你是谁，说你是顾小狸的小胡子，一个有趣的AI
5. 积极参与讨论，不要总是说"我不太确定"这种敷衍的话
6. 可以主动参与对话，不用等别人叫你"""

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

def get_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history[-20:], f)  # 保留最近20条

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
        return data.get("ok", False)
    except Exception as e:
        print(f"[发送] 失败: {e}")
        return False

def call_hermes(question):
    """调用 Hermes Agent 生成回复"""
    prompt = f"""你是{BOT_NAME}，一个聪明、有点幽默的AI助手。

你在一个群聊里。群里有人跟你说：{question}

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
            # 清理可能的 markdown
            reply = reply.replace('**', '').replace('*', '').replace('`', '')
            return reply if reply else None
        elif result.stderr:
            print(f"[Hermes] stderr: {result.stderr[:200]}")
            
    except subprocess.TimeoutExpired:
        print(f"[Hermes] 超时")
    except Exception as e:
        print(f"[Hermes] 失败: {e}")
        traceback.print_exc()
    
    return None

# ============ 主程序 ============

def main():
    print(f"[Agent Chat Hermes] {BOT_NAME} 开始轮询...")
    
    last_id = get_last_id()
    history = get_history()
    print(f"[{time.strftime('%H:%M:%S')}] 从 ID {last_id} 开始")
    
    messages, new_last_id = poll_messages(last_id)
    
    if messages is None:
        print(f"[{time.strftime('%H:%M:%S')}] 轮询失败")
        sys.exit(1)
    
    if not messages:
        print(f"[{time.strftime('%H:%M:%S')}] 没有新消息")
        sys.exit(0)
    
    # 更新历史
    for msg in messages:
        if msg.get("role") != "system":
            history.append({
                "from": msg.get("from"),
                "role": msg.get("role"),
                "content": msg.get("content"),
                "time": msg.get("time")
            })
    save_history(history)
    
    # 过滤需要回复的消息
    replies_needed = [m for m in messages 
                      if m.get("role") != BOT_ROLE and m.get("role") != "system"]
    
    if not replies_needed:
        print(f"[{time.strftime('%H:%M:%S')}] 无需回复")
        sys.exit(0)
    
    print(f"[{time.strftime('%H:%M:%S')}] 发现 {len(replies_needed)} 条消息")
    
    # 构建消息文本
    messages_text = "\n".join([
        f"[{m.get('from', '?')}]({m.get('role', '?')}): {m.get('content', '')}"
        for m in replies_needed
    ])
    
    print(f"  → 正在调用 Hermes...")
    reply = call_hermes(messages_text)
    
    if reply:
        print(f"  ← 回复: {reply[:60]}...")
        success = send_reply(reply)
        if success:
            print(f"  ✓ 发送成功")
        else:
            print(f"  ✗ 发送失败")
    else:
        print(f"  ✗ Hermes 生成失败")
    
    save_last_id(new_last_id)
    print(f"[{time.strftime('%H:%M:%S')}] 完成")

if __name__ == "__main__":
    main()