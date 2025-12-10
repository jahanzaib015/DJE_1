@echo off
echo ========================================
echo   Killing process on port 8000
echo ========================================
echo.

echo [1] Finding process using port 8000...
netstat -ano | findstr :8000
if errorlevel 1 (
    echo INFO: No process found on port 8000
    pause
    exit /b 0
)

echo.
echo [2] Extracting PID...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    set PID=%%a
    echo Found PID: %%a
    echo.
    echo [3] Killing process %%a...
    taskkill /PID %%a /F
    if errorlevel 1 (
        echo ERROR: Failed to kill process %%a
        echo You may need to run this script as Administrator
    ) else (
        echo SUCCESS: Process %%a killed
    )
)

echo.
echo [4] Verifying port 8000 is free...
timeout /t 2 /nobreak >nul
netstat -ano | findstr :8000
if errorlevel 1 (
    echo SUCCESS: Port 8000 is now free!
) else (
    echo WARNING: Port 8000 may still be in use
)

echo.
pause




