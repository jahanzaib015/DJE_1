@echo off
echo Clearing Python cache files...
echo.

REM Clear __pycache__ directories
for /d /r backend %%d in (__pycache__) do @if exist "%%d" (
    echo Removing %%d
    rmdir /s /q "%%d" 2>nul
)

REM Clear .pyc files
for /r backend %%f in (*.pyc) do @if exist "%%f" (
    echo Removing %%f
    del /q "%%f" 2>nul
)

echo.
echo Cache cleared! Please restart your server.
pause








