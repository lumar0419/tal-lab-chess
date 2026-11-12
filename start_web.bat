@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 web_server.py
) else (
    python web_server.py
)
if errorlevel 1 (
    echo.
    echo Python 3 installation is required. Check https://www.python.org/downloads/
    pause
)
