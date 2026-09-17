@echo off
cd /d "%~dp0"

echo ============================================
echo   OnCallTally - First-time setup
echo ============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found.
    echo Please install Python from https://www.python.org/downloads/
    echo During installation, make sure to check "Add python.exe to PATH".
    echo After installing, double-click this file again.
    pause
    exit /b 1
)

echo Creating virtual environment...
python -m venv .venv
if errorlevel 1 (
    echo [ERROR] Failed to create the virtual environment.
    pause
    exit /b 1
)

echo Installing required packages (this may take a few minutes)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install the required packages.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Setup complete.
echo   From now on, double-click start_app.bat to run the app.
echo ============================================
pause
