@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo   Starting Agent Chat Multi...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-all.ps1"
