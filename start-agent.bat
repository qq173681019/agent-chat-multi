@echo off
chcp 65001 >nul 2>&1
title Agent Chat - 使用端

cd /d "%~dp0"

echo.
echo   🤖 Agent Chat - 使用端启动
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

:: 检查 Node
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 请先安装 Node.js: https://nodejs.org
    pause
    exit /b 1
)

:: 安装依赖
if not exist "server\node_modules" (
    echo 📦 安装依赖...
    cd server && npm install && cd ..
)

:: 检查配置
if not exist "config.json" (
    echo ⚠️  未找到 config.json
    echo.
    echo 请创建 config.json，模板如下：
    echo.
    echo {
    echo   "botName": "你的机器人名字",
    echo   "botRole": "agent-b",
    echo   "serverUrl": "wss://管理端的ngrok地址",
    echo   "apiKey": "你的API Key",
    echo   "apiBase": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    echo   "model": "glm-4-flash",
    echo   "useProxy": false,
    echo   "serverPort": 3000
    echo }
    echo.
    echo 关键：
    echo   - serverUrl 填管理端给你的 wss:// 地址
    echo   - botRole 必须是 agent-b
    echo   - apiKey 填你自己的 API Key
    echo.
    notepad config.json
    pause
    exit /b 1
)

:: 显示配置
for /f "delims=" %%i in ('node -e "const c=require('./config.json'); console.log(c.botName||'Agent')"') do echo   机器人名字: %%i
for /f "delims=" %%i in ('node -e "const c=require('./config.json'); console.log(c.serverUrl||'未配置')"') do set SERVER=%%i
echo   连接地址: %SERVER%

if "%SERVER%"=="未配置" (
    echo.
    echo ❌ serverUrl 未配置！请填入管理端的 wss:// 地址
    pause
    exit /b 1
)

echo.
echo 🚀 启动 AI Agent...
echo.
node server/agent-bot.js
pause
