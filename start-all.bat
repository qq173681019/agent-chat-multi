@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo   Starting Agent Chat Multi...
echo.

:: Try python first (most reliable on Windows), then python3, then py
where python >nul 2>nul
if %errorlevel%==0 (
    python -u start_all.py
    goto done
)
where python3 >nul 2>nul
if %errorlevel%==0 (
    python3 -u start_all.py
    goto done
)
where py >nul 2>nul
if %errorlevel%==0 (
    py -u start_all.py
    goto done
)
echo   [ERROR] Python not found! Please install Python first.
echo.
pause
exit /b 1

:done
pause
