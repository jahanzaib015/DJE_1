@echo off
echo ========================================
echo   Starting OCRD Backend Only
echo ========================================
echo.

REM Check if Python is available
py --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python is not installed
        pause
        exit /b 1
    )
    set PYTHON_CMD=python
) else (
    set PYTHON_CMD=py
)

echo [INFO] Activating virtual environment...
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Please run start_local.bat first to set up the environment
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo [INFO] Starting backend on http://localhost:8000
echo [INFO] Press Ctrl+C to stop
echo.

cd backend
%PYTHON_CMD% run.py

pause


