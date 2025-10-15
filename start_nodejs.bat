@echo off
echo 🚀 Starting OCRD Extractor with Node.js frontend
echo 📱 Frontend will be available at: http://localhost:3000
echo 🐍 Backend API will be available at: http://localhost:8000
echo.

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Node.js is not installed or not in PATH
    echo Please install Node.js from https://nodejs.org/
    pause
    exit /b 1
)

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH
    echo Please install Python and ensure it's in PATH
    pause
    exit /b 1
)

REM Install dependencies if needed
if not exist "node_modules" (
    echo 📦 Installing Node.js dependencies...
    npm install
    if errorlevel 1 (
        echo ❌ Failed to install Node.js dependencies
        pause
        exit /b 1
    )
)

if not exist "frontend\node_modules" (
    echo 📦 Installing React dependencies...
    cd frontend
    npm install
    cd ..
    if errorlevel 1 (
        echo ❌ Failed to install React dependencies
        pause
        exit /b 1
    )
)

REM Start the application
echo 🚀 Starting OCRD Extractor...
python run_nodejs.py

pause
