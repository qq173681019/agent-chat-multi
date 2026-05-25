"""
自动检测隧道地址变化，更新 Vercel 代码并推送到 GitHub
用法: python3 -u sync_tunnel.py
建议用 cron 或后台进程持续运行
"""
import requests
import json
import os
import sys
import time
import subprocess
import re

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WS_URL_FILE = os.path.join(SCRIPT_DIR, 'vercel', 'api', 'ws-url.js')
LOG_FILE = os.path.join(SCRIPT_DIR, '.tunnel_sync.log')
VERCEL_API = "https://agent-chat-d1m3.vercel.app/api/ws-url"

POLL_INTERVAL = 60  # 每60秒检查一次


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_current_tunnel():
    """从 cloudflared 日志获取当前隧道地址"""
    log_file = os.path.join(SCRIPT_DIR, 'cloudflared_err.log')
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        matches = re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com', content)
        if matches:
            return matches[-1]
    except:
        pass
    return None


def get_vercel_tunnel():
    """获取 Vercel 上当前的隧道地址"""
    try:
        r = requests.get(VERCEL_API, timeout=10)
        return r.json().get("url", "")
    except:
        return ""


def update_ws_url(new_url):
    """更新 vercel/api/ws-url.js 文件"""
    with open(WS_URL_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # 替换 url 行
    new_content = re.sub(
        r"url: 'https://[a-z0-9-]+\.trycloudflare\.com'",
        f"url: '{new_url}'",
        content
    )

    if new_content == content:
        return False  # 没变化

    # 同时更新 updated 时间戳
    new_content = re.sub(
        r"updated: \d+",
        f"updated: {int(time.time() * 1000)}",
        new_content
    )

    with open(WS_URL_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)
    return True


def git_push():
    """Git commit 并 push"""
    try:
        subprocess.run(['git', 'add', 'vercel/api/ws-url.js'],
            cwd=SCRIPT_DIR, capture_output=True, timeout=10)
        result = subprocess.run(
            ['git', 'commit', '-m', f'auto: update tunnel URL ({time.strftime("%H:%M")})'],
            cwd=SCRIPT_DIR, capture_output=True, timeout=10)
        if 'nothing to commit' in (result.stdout or '').decode('utf-8', errors='ignore'):
            return False
        subprocess.run(['git', 'push'],
            cwd=SCRIPT_DIR, capture_output=True, timeout=30)
        return True
    except Exception as e:
        log(f"git push 失败: {e}")
        return False


def main():
    log("🔄 隧道同步守护进程启动")
    log(f"   检查间隔: {POLL_INTERVAL}秒")

    while True:
        try:
            current = get_current_tunnel()
            vercel = get_vercel_tunnel()

            if not current:
                log("⚠️ 无法获取当前隧道地址，跳过")
            elif current != vercel:
                log(f"🔄 检测到变化!")
                log(f"   本地: {current}")
                log(f"   远程: {vercel}")
                if update_ws_url(current):
                    if git_push():
                        log(f"✅ 已更新并推送到 GitHub: {current}")
                    else:
                        log(f"❌ 推送失败")
                else:
                    log(f"⚠️ 文件更新失败")
            else:
                pass  # 地址一致，无需操作

        except Exception as e:
            log(f"❌ 错误: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
