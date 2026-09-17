@echo off
cd /d "%~dp0"
title OnCallTally

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Setup has not been completed yet.
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)

echo Starting OnCallTally. Your browser will open automatically in a moment...
echo Closing this window will stop the app.
echo When you are done, please close this window.
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:5000"
".venv\Scripts\python.exe" app.py

pause
