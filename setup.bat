@echo off
cd /d "%~dp0"

echo ============================================
echo   OnCallTally - First-time setup
echo ============================================
echo.

python -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found, or is not set up correctly.
    echo.
    echo This can happen even when a "python" command exists, if it is only
    echo the Microsoft Store placeholder ^(which opens the Store instead of
    echo running Python^) rather than a real Python installation.
    echo.
    echo Please install Python from https://www.python.org/downloads/
    echo During installation, make sure to check "Add python.exe to PATH".
    echo After installing, close this window and double-click this file again.
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
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] The virtual environment was not created correctly.
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
