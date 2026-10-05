@echo off
REM Double-click to start JarvisBuddy. First run sets everything up.
cd /d "%~dp0"
if not exist .venv (
    echo Setting up JarvisBuddy for the first time...
    python -m venv .venv || goto :nopython
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
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
