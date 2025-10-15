@echo off
echo 🚀 OCRD Extractor - Windows Installation
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

echo ✅ Python found
echo.

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ❌ Failed to create virtual environment
        pause
        exit /b 1
    )
    echo ✅ Virtual environment created
) else (
    echo ✅ Virtual environment already exists
)

echo.
echo 🔧 Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ❌ Failed to activate virtual environment
    pause
    exit /b 1
)

echo ✅ Virtual environment activated
echo.

REM Upgrade pip first
echo 📦 Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo ❌ Failed to upgrade pip
    pause
    exit /b 1
)

echo.
echo 📦 Installing dependencies (this may take a few minutes)...
echo Installing backend dependencies...

REM Install backend dependencies with specific versions to avoid compilation issues
pip install --no-cache-dir -r backend\requirements_simple.txt
if errorlevel 1 (
    echo ❌ Failed to install backend dependencies
    echo.
    echo 🔄 Trying alternative installation method...
    pip install --no-cache-dir --only-binary=all -r backend\requirements_simple.txt
    if errorlevel 1 (
        echo ❌ Alternative installation also failed
        pause
        exit /b 1
    )
)

echo.
echo 📦 Installing frontend dependencies...
pip install --no-cache-dir -r requirements.txt
if errorlevel 1 (
    echo ❌ Failed to install frontend dependencies
    pause
    exit /b 1
)

echo.
echo ✅ All dependencies installed successfully!
echo.
echo 🚀 Starting OCRD Extractor...
echo 📄 Main app: http://localhost:8000
echo 📚 API docs: http://localhost:8000/docs
echo ========================================
echo.

REM Start the server
cd backend
python run.py

pause
