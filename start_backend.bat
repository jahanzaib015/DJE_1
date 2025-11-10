@echo off
REM Helper script to start backend with proper Python command
cd /d "%~dp0"
call venv\Scripts\activate.bat
cd backend
py run.py
pause


