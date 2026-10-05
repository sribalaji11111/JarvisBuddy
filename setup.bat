@echo off
REM Double-click once: installs every library and downloads the speech model and offline brain.
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv || goto :nopython
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if not exist .env copy .env.example .env >nul
python -m jarvisbuddy --setup
pause
exit /b

:nopython
echo Python was not found. Install Python 3.10+ from https://www.python.org/downloads/ and tick "Add to PATH".
pause
