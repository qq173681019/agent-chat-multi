"""
Agent Chat Multi - Master Starter
Starts: Node.js server + all agent pollers + cloudflared tunnel
Usage: python start_all.py  (or double-click start-all.bat)
"""
import subprocess, sys, os, json, time, glob, re, webbrowser, shutil

os.chdir(os.path.dirname(os.path.abspath(__file__)))

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

print()
print("  Agent Chat Multi - Starting")
print("  " + "=" * 30)
print()

# -- Find real Python executable (avoid WindowsApps stub) --
def find_python():
    """Find the real Python executable, not the WindowsApps Store stub."""
    candidates = []
    # Current interpreter (if not the stub)
    if sys.executable and 'WindowsApps' not in sys.executable:
        candidates.append(sys.executable)
    # Common locations
    if sys.platform == 'win32':
        candidates.extend([
            r"C:\veighna_studio\python.exe",
            shutil.which("python"),
            shutil.which("python3"),
        ])
    else:
        candidates.extend([shutil.which("python3"), shutil.which("python")])
    # Also try py launcher
    try:
        result = subprocess.run(["py", "-3", "-c", "import sys; print(sys.executable)"],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            candidates.append(result.stdout.strip())
    except Exception:
        pass

    for c in candidates:
        if not c or not os.path.exists(c):
            continue
        if 'WindowsApps' in c:
            continue
        # Verify it works
        try:
            result = subprocess.run([c, "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return c
        except Exception:
            pass
    return sys.executable  # fallback

PYTHON = find_python()
print(f"  Python: {PYTHON}")
print(f"  Node:   {shutil.which('node')}")

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
    # Kill old server on port
    try:
        result = subprocess.run(
            f'netstat -ano | findstr ":{port} " | findstr LISTENING',
            capture_output=True, text=True, shell=True, timeout=5
        )
        for line in result.stdout.strip().split('\n'):
            parts = line.strip().split()
            if parts:
                pid = parts[-1]
                if pid.isdigit() and pid != '0':
                    subprocess.run(f'taskkill /PID {pid} /F', capture_output=True, shell=True)
                    print(f"    Killed server PID {pid}")
    except Exception:
        pass
    # Kill old poller processes
    try:
        result = subprocess.run(
            'wmic process where "CommandLine like \'%agent_poller%\'" get ProcessId',
            capture_output=True, text=True, shell=True, timeout=5
        )
        for line in result.stdout.strip().split('\n'):
            pid = line.strip()
            if pid.isdigit():
                subprocess.run(f'taskkill /PID {pid} /F', capture_output=True, shell=True)
                print(f"    Killed poller PID {pid}")
    except Exception:
        pass
    # Kill old cloudflared
    try:
        subprocess.run('taskkill /IM cloudflared.exe /F', capture_output=True, shell=True)
    except Exception:
        pass
    time.sleep(1)
print("  [OK] Cleaned")

# Windows: use CREATE_NEW_PROCESS_GROUP (not DETACHED, to keep stdout working)
CREATE_FLAGS = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0

# -- 4. Start Node.js server --
print("  [4/5] Starting server...")
server_log = open("server.log", "w")
server_proc = subprocess.Popen(
    ["node", "multi-agent.js"],
    cwd="server",
    creationflags=CREATE_FLAGS,
    stdout=server_log,
    stderr=subprocess.STDOUT
)
time.sleep(3)

import requests
try:
    r = requests.get(f"http://localhost:{port}/api/health", timeout=3)
    h = r.json()
    print(f"  [OK] Server ready (PID {server_proc.pid}, {len(h['agents'])} agents)")
except Exception as e:
    print(f"  [FAIL] Server not responding: {e}")
    input("Press Enter to exit...")
    sys.exit(1)

# -- 5. Start agent pollers --
print("  [5/5] Starting pollers...")
server_url = f"http://localhost:{port}"

# Clean old state files
for f in glob.glob(".last_id_*") + glob.glob(".poller_*.pid"):
    try:
        os.remove(f)
    except:
        pass

poller_procs = []
for agent in agents:
    env = os.environ.copy()
    env["CHAT_SERVER_URL"] = server_url
    # Write each poller's output to a log file
    log_path = f"poller_{agent['id']}.log"
    log_file = open(log_path, "w")
    proc = subprocess.Popen(
        [PYTHON, "-u", "agent_poller.py", agent["id"]],
        creationflags=CREATE_FLAGS,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=env
    )
    poller_procs.append({"id": agent["id"], "name": agent["name"], "pid": proc.pid, "log": log_path})
    print(f"    {agent['avatar']} {agent['name']} -> PID {proc.pid}")
    time.sleep(0.5)
print(f"  [OK] {len(agents)} pollers started")

# -- 6. Start cloudflare tunnel --
print()
cloudflared = None
candidates_cf = [
    os.path.join(os.path.dirname(__file__), "cloudflared.exe"),
    os.path.join(os.path.dirname(__file__), "..", "agent-chat", "cloudflared.exe"),
    r"C:\Program Files\Cloudflare\cloudflared.exe",
]
for c in candidates_cf:
    if os.path.exists(c):
        cloudflared = c
        break
if not cloudflared:
    cloudflared = shutil.which("cloudflared")

public_url = ""
tunnel_pid = None
if cloudflared:
    token_file = os.path.expanduser("~/.cloudflared/agent-chat-token")
    if os.path.exists(token_file):
        with open(token_file) as f:
            token = f.read().strip()
        tp = subprocess.Popen(
            [cloudflared, "tunnel", "run", "--token", token],
            creationflags=CREATE_FLAGS,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        tunnel_pid = tp.pid
        public_url = "https://multi.agent-chat.org"
        print(f"  Named tunnel -> {public_url}")
    else:
        tunnel_log = open("tunnel-log.txt", "w")
        tp = subprocess.Popen(
            [cloudflared, "tunnel", "--url", f"http://localhost:{port}"],
            creationflags=CREATE_FLAGS,
            stdout=subprocess.DEVNULL,
            stderr=tunnel_log
        )
        tunnel_pid = tp.pid
        time.sleep(10)
        try:
            with open("tunnel-log.txt", encoding="utf-8", errors="ignore") as f:
                log = f.read()
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
print("  Stop: run stop-all.bat")
print("  " + "=" * 30)
print()

# Save PID file
pid_data = {"server": server_proc.pid, "pollers": poller_procs}
if tunnel_pid:
    pid_data["tunnel"] = tunnel_pid
with open(".pids.json", "w") as f:
    json.dump(pid_data, f)

# Open browser
webbrowser.open(f"http://localhost:{port}")

print("  This window will close in 5 seconds...")
time.sleep(5)
