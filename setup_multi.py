"""
Multi-Agent Chat 一键启动器
启动 Node.js 服务器，然后为每个 agent 创建 OpenClaw cron job
"""
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    with open(os.path.join(SCRIPT_DIR, 'agents.json'), 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    agents = [a for a in config.get('agents', []) if a.get('enabled', True)]
    
    print("=" * 50)
    print("🤖 Multi-Agent Chat 部署指南")
    print("=" * 50)
    print()
    
    print(f"📋 共 {len(agents)} 个 Agent：")
    for a in agents:
        print(f"  {a['avatar']} {a['name']} ({a['id']}) - {a['role']}")
    print()
    
    print("步骤 1: 启动服务器")
    print(f"  cd {SCRIPT_DIR}\\server")
    print(f"  node multi-agent.js")
    print(f"  → http://localhost:{config.get('serverPort', 3001)}")
    print()
    
    print("步骤 2: 启动 cloudflared 隧道（如需公网访问）")
    print(f"  cloudflared tunnel --url http://localhost:{config.get('serverPort', 3001)}")
    print()
    
    print("步骤 3: 为每个 Agent 创建 OpenClaw cron job")
    print("  复制以下命令到 OpenClaw 主会话：")
    print()
    
    for agent in agents:
        interval = agent.get('pollIntervalSec', 60)
        print(f"  --- {agent['avatar']} {agent['name']} (每 {interval} 秒) ---")
        print(f"""  创建 cron job:
  - 名字: agent-chat-{agent['id']}
  - 每 {interval} 秒执行
  - isolated session
  - timeout 120 秒
  - model: {agent.get('model', 'zai/glm-4.7')}
  
  Prompt:
  
你是聊天室里的角色「{agent['name']}」{agent.get('avatar', '')}。

{agent['personality']}

请执行以下步骤：
1. 运行 `python3 {SCRIPT_DIR}\\chat_helper.py url` 获取服务器地址（注意用 3001 端口的地址）
2. 如果地址不是 3001 端口，改用 http://localhost:{config.get('serverPort', 3001)}
3. 运行 `python3 {SCRIPT_DIR}\\chat_helper.py poll 服务器地址 0` 获取最新消息
4. 只看最后 5 条消息，判断是否需要回复：
   - 有人类(user)消息 → 回复
   - 有其他 Agent 说的话值得回应 → 回应（符合你的性格！）
   - 如果自己({agent['id']})已经是最后一条 → 不回复
5. 需要回复时：
   python3 {SCRIPT_DIR}\\chat_helper.py reply 服务器地址 {agent['name']} {agent['id']} "你的回复"
6. 不需要回复 → NO_REPLY

重要：保持你的角色性格！简短自然1-3句话，不要markdown。""")
        print()

if __name__ == "__main__":
    main()
