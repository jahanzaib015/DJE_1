@echo off
echo 🚀 OCRD Extractor Environment Setup
echo ====================================
echo.

echo 📝 Setting up environment files...
python setup_environment.py

echo.
echo 🔍 Checking environment...
python check_environment.py

echo.
echo ✅ Setup complete! 
echo.
echo 🚀 To start the application:
echo    - Run: start_nodejs.bat
echo    - Or: python run_nodejs.py
echo.
pause
