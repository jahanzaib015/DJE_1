@echo off
echo ========================================
echo   OCRD Extractor - Local Deployment
echo ========================================
echo.

REM Check if Python is available
py --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python is not installed or not in PATH
        echo Please install Python 3.8+ from https://www.python.org/
        pause
        exit /b 1
    )
    set PYTHON_CMD=python
) else (
    set PYTHON_CMD=py
)

REM Check if Node.js is available
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js is not installed or not in PATH
    echo Please install Node.js from https://nodejs.org/
    pause
    exit /b 1
)

echo [INFO] Checking virtual environment...
if not exist "venv\Scripts\activate.bat" (
    echo [INFO] Creating virtual environment...
    %PYTHON_CMD% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
)

echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

echo [INFO] Installing Python dependencies...
pip install -q --upgrade pip
echo [INFO] Installing dependencies (this may take a few minutes)...
pip install -q --only-binary=:all: -r backend\requirements.txt
if errorlevel 1 (
    echo [WARNING] Some dependencies failed with binary-only install, trying normal install...
    pip install -q -r backend\requirements.txt
    if errorlevel 1 (
        echo [WARNING] Some Python dependencies may have failed. Continuing anyway...
    )
)

echo [INFO] Installing Node.js dependencies...
if not exist "node_modules" (
    call npm install
    if errorlevel 1 (
        echo [ERROR] Failed to install Node.js dependencies
        pause
        exit /b 1
    )
)

if not exist "frontend\node_modules" (
    echo [INFO] Installing React dependencies...
    cd frontend
    call npm install
    cd ..
    if errorlevel 1 (
        echo [ERROR] Failed to install React dependencies
        pause
        exit /b 1
    )
)

echo.
echo [INFO] Starting services...
echo [INFO] Backend API will be available at: http://localhost:8000
echo [INFO] Frontend will be available at: http://localhost:3000
echo [INFO] API docs will be available at: http://localhost:8000/docs
echo.
echo Press Ctrl+C to stop all services
echo.

REM Start Python backend in background
REM Use py launcher (preferred on Windows)
start "OCRD Backend" cmd /k "venv\Scripts\activate.bat && cd backend && py run.py"

REM Wait a moment for backend to start
timeout /t 3 /nobreak >nul

REM Start React frontend (development server)
start "OCRD Frontend" cmd /k "cd frontend && npm start"

echo.
echo [SUCCESS] Services are starting!
echo [INFO] Please wait a few seconds for services to fully start
echo [INFO] Then open http://localhost:3000 in your browser
echo.
pause

