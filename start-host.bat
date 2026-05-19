@echo off
chcp 65001 >nul 2>&1
title Agent Chat - 管理端

cd /d "%~dp0"

echo.
echo   🏠 Agent Chat - 管理端启动
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
    echo ⚠️  未找到 config.json，从模板创建...
    copy config.example.json config.json
    echo 📝 请编辑 config.json 填入你的 API Key，然后重新运行
    notepad config.json
    pause
    exit /b 1
)

:: 读取端口
for /f "delims=" %%i in ('node -e "const c=require('./config.json'); console.log(c.serverPort||3000)"') do set PORT=%%i

echo 🚀 [1/3] 启动聊天服务器 (端口 %PORT%)...
start /b node server/index.js
timeout /t 2 /nobreak >nul

echo 🤖 [2/3] 启动 AI Agent...
start /b node server/agent-bot.js
timeout /t 2 /nobreak >nul

echo 🌐 [3/3] 检查公网隧道...
echo.
echo   ═══════════════════════════════════════
echo   ✅ 本地访问: http://localhost:%PORT%
echo   💡 安装 ngrok 获得公网地址: https://ngrok.com
echo   ═══════════════════════════════════════
echo.

:: 打开浏览器
start http://localhost:%PORT%

echo   按 Ctrl+C 停止所有服务
pause
