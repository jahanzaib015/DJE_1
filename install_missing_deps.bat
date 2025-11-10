@echo off
echo Installing missing dependencies...
echo.

REM Check if Python is available
py --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Python not found
        pause
        exit /b 1
    )
    set PYTHON_CMD=python
) else (
    set PYTHON_CMD=py
)

echo [1] Creating virtual environment if needed...
if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv venv
)

echo [2] Activating virtual environment...
call venv\Scripts\activate.bat

echo [3] Installing chromadb...
pip install chromadb==0.4.24

echo [4] Installing any other missing dependencies...
pip install -r backend\requirements.txt

echo.
echo Done! Try starting the backend now.
pause


