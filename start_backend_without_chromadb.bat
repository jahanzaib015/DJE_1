@echo off
echo ========================================
echo   Starting Backend (ChromaDB Optional)
echo ========================================
echo.
echo Note: ChromaDB is optional - the backend will work
echo in mock mode if ChromaDB is not installed.
echo.

REM Check if Python is available
py --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python not found
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
    echo Please run: %PYTHON_CMD% -m venv venv
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


