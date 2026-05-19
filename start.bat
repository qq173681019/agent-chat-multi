@echo off
chcp 65001 >nul 2>&1
title Agent Chat

cd /d "%~dp0"

:: 检查 Node.js
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

echo.
echo ╔══════════════════════════════════════╗
echo ║   🤖 Agent Chat 启动中...            ║
echo ╚══════════════════════════════════════╝
echo.

:: 读取端口
for /f "delims=" %%i in ('node -e "const c=require('./config.json'); console.log(c.serverPort||3000)"') do set PORT=%%i

:: 启动服务器
echo [1/2] 启动聊天服务器 (端口 %PORT%)...
start /b node server/index.js
timeout /t 2 /nobreak >nul

:: 启动 Agent Bot
echo [2/2] 启动 AI Agent...
start /b node server/agent-bot.js
timeout /t 2 /nobreak >nul

echo.
echo ══════════════════════════════════════
echo   ✅ 本地访问: http://localhost:%PORT%
echo   💡 如需公网访问，请安装 ngrok: https://ngrok.com
echo ══════════════════════════════════════
echo.
echo 按 Ctrl+C 停止所有服务

:: 打开浏览器
start http://localhost:%PORT%

:: 等待
pause
