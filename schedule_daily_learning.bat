@echo off
REM Optional: let Jarvis learn from your day automatically every night at 23:00.
REM Remove it later with:  schtasks /delete /tn "JarvisBuddy daily learning" /f
cd /d "%~dp0"
schtasks /create /tn "JarvisBuddy daily learning" /sc daily /st 23:00 /f ^
  /tr "cmd /c cd /d \"%~dp0\" && \"%~dp0.venv\Scripts\python.exe\" -m jarvisbuddy --learn >> \"%USERPROFILE%\.jarvisbuddy\learning.log\" 2>&1"
echo Scheduled: every day at 23:00.
pause
