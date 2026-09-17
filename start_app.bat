@echo off
cd /d "%~dp0"
title OnCallTally

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Setup has not been completed yet.
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)

echo ============================================
echo   OnCallTally is starting...
echo   Your browser should open automatically.
echo.
echo   If it does NOT open within a few seconds,
echo   please open your browser manually and go to:
echo.
echo       http://127.0.0.1:5000
echo.
echo   Closing this window will stop the app.
echo   When you are done, please close this window.
echo ============================================
echo.

start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:5000"
".venv\Scripts\python.exe" app.py

pause
