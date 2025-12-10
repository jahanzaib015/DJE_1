@echo off
echo ========================================
echo   Error Diagnostics
echo ========================================
echo.

echo [1] Checking Python...
py --version
if errorlevel 1 (
    echo ERROR: Python not found
    python --version
)

echo.
echo [2] Checking virtual environment...
if exist "venv\Scripts\activate.bat" (
    echo OK: Virtual environment exists
) else (
    echo ERROR: Virtual environment not found
)

echo.
echo [3] Checking if backend dependencies are installed...
call venv\Scripts\activate.bat 2>nul
if errorlevel 1 (
    echo ERROR: Cannot activate virtual environment
) else (
    pip show fastapi >nul 2>&1
    if errorlevel 1 (
        echo ERROR: FastAPI not installed
    ) else (
        echo OK: FastAPI installed
    )
    
    pip show uvicorn >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Uvicorn not installed
    ) else (
        echo OK: Uvicorn installed
    )
)

echo.
echo [4] Testing backend import...
call venv\Scripts\activate.bat 2>nul
cd backend
py -c "import sys; sys.path.insert(0, 'app'); from app.main import app; print('OK: Backend imports successfully')" 2>&1
if errorlevel 1 (
    echo ERROR: Backend import failed - see error above
)

echo.
echo [5] Checking port 8000...
netstat -ano | findstr :8000
if errorlevel 1 (
    echo INFO: Port 8000 is free
) else (
    echo WARNING: Port 8000 is already in use
)

echo.
echo ========================================
echo   Please copy the error output above
echo   and share it with me
echo ========================================
pause






