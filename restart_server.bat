@echo off
echo ========================================
echo   Restarting OCRD Extractor Server
echo ========================================
echo.

echo [1/3] Clearing Python cache...
for /d /r backend %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
for /r backend %%f in (*.pyc) do @if exist "%%f" del /q "%%f" 2>nul
echo    Cache cleared!
echo.

echo [2/3] Stopping existing server processes...
REM Try to find and kill processes on port 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo    Killing process %%a on port 8000...
    taskkill /F /PID %%a >nul 2>&1
)
echo    Done!
echo.

echo [3/3] Starting server with auto-reload enabled...
echo    Server will reload automatically when you change code files
echo    Press Ctrl+C to stop the server
echo.
cd backend
python run.py
pause






