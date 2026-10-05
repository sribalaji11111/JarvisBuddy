@echo off
REM Double-click to start JarvisBuddy. The first run sets everything up (libraries and models).
cd /d "%~dp0"
if not exist .venv (
    echo Setting up JarvisBuddy for the first time...
    python -m venv .venv || goto :nopython
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    if not exist .env copy .env.example .env >nul
    python -m jarvisbuddy --setup
) else (
    call .venv\Scripts\activate.bat
)
if not exist .env copy .env.example .env >nul
python -m jarvisbuddy %*
pause
exit /b

:nopython
echo Python was not found. Install Python 3.10+ from https://www.python.org/downloads/ and tick "Add to PATH".
pause
