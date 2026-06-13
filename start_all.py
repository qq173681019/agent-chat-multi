"""
Agent Chat Multi - Master Starter
Starts: Node.js server + all agent pollers + cloudflared tunnel
Usage: python3 start_all.py
"""
import subprocess, sys, os, json, time, glob, signal

os.chdir(os.path.dirname(os.path.abspath(__file__)))

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

print()
print("  Agent Chat Multi - Starting")
print("  " + "=" * 30)
print()

# -- 1. Install deps --
if not os.path.exists("server/node_modules"):
    print("  [1/5] Installing npm deps...")
    subprocess.run(["npm", "install"], cwd="server", shell=True)
else:
    print("  [1/5] Deps OK")

# -- 2. Read config --
with open("agents.json", encoding="utf-8") as f:
    cfg = json.load(f)
port = cfg.get("serverPort", 3001)
agents = [a for a in cfg["agents"] if a.get("enabled", True)]
print(f"  [2/5] Port: {port}, Agents: {len(agents)}")

# -- 3. Kill old processes on port --
print("  [3/5] Cleaning old processes...")
if sys.platform == 'win32':
    try:
        result = subprocess.run(f'netstat -ano | findstr ":{port} " | findstr LISTENING',
                                capture_output=True, text=True, shell=True, timeout=5)
        for line in result.stdout.strip().split('\n'):
            parts = line.strip().split()
            if parts:
                pid = parts[-1]
                if pid.isdigit() and pid != '0':
                    subprocess.run(f'taskkill /PID {pid} /F', capture_output=True, shell=True)
                    print(f"    Killed PID {pid}")
    except Exception:
        pass
    time.sleep(1)
print("  [OK] Port cleaned")

# -- 4. Start Node.js server --
print("  [4/5] Starting server...")
server_proc = subprocess.Popen(
    ["node", "multi-agent.js"],
    cwd="server",
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(3)

import requests
try:
    r = requests.get(f"http://localhost:{port}/api/health", timeout=3)
    h = r.json()
    print(f"  [OK] Server ready (PID {server_proc.pid}, {len(h['agents'])} agents)")
except Exception as e:
    print(f"  [FAIL] Server not responding: {e}")
    sys.exit(1)

# -- 5. Start agent pollers --
print("  [5/5] Starting pollers...")
os.environ["CHAT_SERVER_URL"] = f"http://localhost:{port}"

# Clean old state files
for f in glob.glob(".last_id_*") + glob.glob(".poller_*.pid"):
    try: os.remove(f)
    except: pass

poller_procs = []
for agent in agents:
    proc = subprocess.Popen(
        [sys.executable, "-u", "agent_poller.py", agent["id"]],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    poller_procs.append({"id": agent["id"], "name": agent["name"], "pid": proc.pid})
    print(f"    {agent['avatar']} {agent['name']} -> PID {proc.pid}")
    time.sleep(0.3)
print(f"  [OK] {len(agents)} pollers started")

# -- 6. Start cloudflare tunnel --
print()
cloudflared = None
candidates = [
    os.path.join(os.path.dirname(__file__), "cloudflared.exe"),
    os.path.join(os.path.dirname(__file__), "..", "agent-chat", "cloudflared.exe"),
    r"C:\Program Files\Cloudflare\cloudflared.exe",
]
for c in candidates:
    if os.path.exists(c):
        cloudflared = c
        break
if not cloudflared:
    import shutil
    cloudflared = shutil.which("cloudflared")

public_url = ""
if cloudflared:
    token_file = os.path.expanduser("~/.cloudflared/agent-chat-token")
    if os.path.exists(token_file):
        with open(token_file) as f:
            token = f.read().strip()
        subprocess.Popen([cloudflared, "tunnel", "run", "--token", token],
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        public_url = "https://multi.agent-chat.org"
        print(f"  Named tunnel -> {public_url}")
    else:
        tunnel_proc = subprocess.Popen(
            [cloudflared, "tunnel", "--url", f"http://localhost:{port}"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
            stdout=subprocess.DEVNULL,
            stderr=open("tunnel-log.txt", "w")
        )
        time.sleep(10)
        try:
            with open("tunnel-log.txt", encoding="utf-8", errors="ignore") as f:
                log = f.read()
            import re
            match = re.search(r'(https://[a-z0-9-]+\.trycloudflare\.com)', log)
            if match:
                public_url = match.group(1)
                print(f"  Quick tunnel -> {public_url}")
        except Exception:
            print("  Tunnel starting... check tunnel-log.txt")
else:
    print("  cloudflared not found, local only")

# -- Summary --
print()
print("  " + "=" * 30)
print("  All systems go!")
print()
print(f"  Local:  http://localhost:{port}")
if public_url:
    print(f"  Public: {public_url}")
print()
print(f"  Server PID: {server_proc.pid}")
for p in poller_procs:
    print(f"  {p['name']} PID: {p['pid']}")
print()
print("  Stop: Ctrl+C or run stop_all.py")
print("  " + "=" * 30)
print()

# Open browser
import webbrowser
webbrowser.open(f"http://localhost:{port}")

# Write PID file for stop_all.py
with open(".pids.json", "w") as f:
    json.dump({"server": server_proc.pid, "pollers": poller_procs}, f)

# Keep alive
try:
    print("  (Press Ctrl+C to stop)")
    while True:
        time.sleep(60)
except KeyboardInterrupt:
    print("\n  Stopping...")
    for p in poller_procs:
        try: os.kill(p["pid"], signal.SIGTERM)
        except: pass
    try: server_proc.terminate()
    except: pass
    print("  Stopped.")
