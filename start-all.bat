@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo   正在启动 Agent Chat Multi...
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0start-all.ps1"
