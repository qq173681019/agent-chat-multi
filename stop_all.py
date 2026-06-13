"""
Agent Chat Multi - Stop All
Usage: python3 stop_all.py
"""
import subprocess, sys, os, json, signal

os.chdir(os.path.dirname(os.path.abspath(__file__)))
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

print()
print("  Stopping Agent Chat Multi...")

# Read port
port = 3001
try:
    with open("agents.json", encoding="utf-8") as f:
        cfg = json.load(f)
    port = cfg.get("serverPort", 3001)
except: pass

# Kill by PID file
if os.path.exists(".pids.json"):
    with open(".pids.json") as f:
        pids = json.load(f)
    for p in pids.get("pollers", []):
        try: os.kill(p["pid"], signal.SIGTERM)
        except: pass
    sp = pids.get("server")
    if sp:
        try: os.kill(sp, signal.SIGTERM)
        except: pass
    os.remove(".pids.json")

# Kill anything on port
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
    except: pass

    # Kill agent_poller processes
    try:
        result = subprocess.run('wmic process where "CommandLine like \'%agent_poller%\'" get ProcessId',
                                capture_output=True, text=True, shell=True, timeout=5)
        for line in result.stdout.strip().split('\n'):
            pid = line.strip()
            if pid.isdigit():
                subprocess.run(f'taskkill /PID {pid} /F', capture_output=True, shell=True)
    except: pass

    # Kill cloudflared
    try:
        subprocess.run('taskkill /IM cloudflared.exe /F', capture_output=True, shell=True)
    except: pass

print("  All stopped.")
print()
