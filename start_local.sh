#!/bin/bash

echo "========================================"
echo "  OCRD Extractor - Local Deployment"
echo "========================================"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed or not in PATH"
    echo "Please install Python 3.8+ from https://www.python.org/"
    exit 1
fi

# Check if Node.js is available
if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js is not installed or not in PATH"
    echo "Please install Node.js from https://nodejs.org/"
    exit 1
fi

echo "[INFO] Checking virtual environment..."
if [ ! -d "venv" ]; then
    echo "[INFO] Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create virtual environment"
        exit 1
    fi
fi

echo "[INFO] Activating virtual environment..."
source venv/bin/activate

echo "[INFO] Installing Python dependencies..."
pip install -q --upgrade pip
pip install -q -r backend/requirements.txt
if [ $? -ne 0 ]; then
    echo "[WARNING] Some Python dependencies may have failed. Continuing..."
fi

echo "[INFO] Installing Node.js dependencies..."
if [ ! -d "node_modules" ]; then
    npm install
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to install Node.js dependencies"
        exit 1
    fi
fi

if [ ! -d "frontend/node_modules" ]; then
    echo "[INFO] Installing React dependencies..."
    cd frontend
    npm install
    cd ..
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to install React dependencies"
        exit 1
    fi
fi

echo ""
echo "[INFO] Starting services..."
echo "[INFO] Backend API will be available at: http://localhost:8000"
echo "[INFO] Frontend will be available at: http://localhost:3000"
echo "[INFO] API docs will be available at: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Start Python backend in background
cd backend
source ../venv/bin/activate
python run.py &
BACKEND_PID=$!
cd ..

# Wait a moment for backend to start
sleep 3

# Start React frontend (development server) in background
cd frontend
npm start &
FRONTEND_PID=$!
cd ..

echo ""
echo "[SUCCESS] Services are starting!"
echo "[INFO] Backend PID: $BACKEND_PID"
echo "[INFO] Frontend PID: $FRONTEND_PID"
echo "[INFO] Please wait a few seconds for services to fully start"
echo "[INFO] Then open http://localhost:3000 in your browser"
echo ""

# Wait for Ctrl+C
trap "echo ''; echo '[INFO] Stopping services...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT
wait

