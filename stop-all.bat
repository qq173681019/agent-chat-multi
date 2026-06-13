@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0stop-all.ps1"
