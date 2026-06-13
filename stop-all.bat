@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
python3 stop_all.py
