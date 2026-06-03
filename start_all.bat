@echo off
chcp 65001 >nul 2>&1
title Agent Chat - All Characters

echo.
echo ╔══════════════════════════════════════════╗
echo ║   🤖 Agent Chat - Starting All Agents   ║
echo ╚══════════════════════════════════════════╝
echo.

cd /d "%~dp0"

REM 检查 .env
if not exist ".env" (
    echo ❌ .env 文件不存在！请复制 .env.example 并填写 API Key
    pause
    exit /b 1
)

REM 检查 agents.json
if not exist "agents.json" (
    echo ❌ agents.json 不存在！
    pause
    exit /b 1
)

echo 📋 启动角色:
echo.

REM 读取 agents.json 中的 enabled agents 并逐个启动
for /f "usebackq delims=" %%i in (`python3 -c "import json,sys;agents=json.load(open('agents.json','r',encoding='utf-8')).get('agents',[]);print(' '.join(a['id'] for a in agents if a.get('enabled',True)))"`) do set AGENTS=%%i

for %%a in (%AGENTS%) do (
    for /f "usebackq delims=" %%n in (`python3 -c "import json;agents=json.load(open('agents.json','r',encoding='utf-8')).get('agents',[]);a=next((x for x in agents if x['id']=='%%a'),None);print(a['avatar']+' '+a['name'] if a else '??')" 2^>nul`) do echo   %%n ^(%%a^)
    start "Agent: %%a" /min python3 -u agent_poller.py %%a
    timeout /t 2 /nobreak >nul
)

echo.
echo ✅ 全部启动完成！(各角色在独立最小化窗口运行)
echo.
echo 💡 关闭角色窗口即可停止对应角色
echo 💡 或运行 stop_all.bat 停止全部
echo.
pause
