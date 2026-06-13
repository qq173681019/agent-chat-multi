@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo   Starting Agent Chat Multi...
echo.
python3 -u start_all.py
pause
