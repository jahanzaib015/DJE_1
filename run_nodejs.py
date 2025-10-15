#!/usr/bin/env python3
"""
Run OCRD Extractor with Node.js frontend and Python backend
"""

import socket
import subprocess
import sys
import time
import os
import signal
import threading
from pathlib import Path

def find_free_port():
    """Find a free port to use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port

def run_python_backend():
    """Run the Python FastAPI backend"""
    print("Starting Python backend...")
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "backend.app.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload"
        ])
    except KeyboardInterrupt:
        print("\nPython backend stopped")

def run_nodejs_frontend():
    """Run the Node.js frontend"""
    print("Starting Node.js frontend...")

    try:
        # Ensure we're inside the frontend directory if it exists
        frontend_dir = Path("frontend")
        cwd = frontend_dir if frontend_dir.exists() else Path.cwd()

        # Install dependencies if needed
        if not (cwd / "node_modules").exists():
            print("Installing Node.js dependencies...")
            subprocess.run(["npm", "install"], check=True, shell=True, cwd=cwd)

        # Optional: install React dependencies if you use install-all script
        if (cwd / "frontend").exists() and not (cwd / "frontend/node_modules").exists():
            print("Installing React dependencies...")
            subprocess.run(["npm", "run", "install-all"], check=True, shell=True, cwd=cwd)

        # Start the Node.js server
        subprocess.run(["npm", "start"], check=True, shell=True, cwd=cwd)

    except KeyboardInterrupt:
        print("\nNode.js frontend stopped")

def main():
    """Run both Python backend and Node.js frontend"""
    print("Starting OCRD Extractor with Node.js frontend")
    print("Frontend will be available at: http://localhost:3000")
    print("Backend API will be available at: http://localhost:8000")
    print("Press Ctrl+C to stop both servers")

    backend_thread = threading.Thread(target=run_python_backend, daemon=True)
    backend_thread.start()

    # Wait a moment for backend to start
    time.sleep(3)

    try:
        run_nodejs_frontend()
    except KeyboardInterrupt:
        print("\nShutting down OCRD Extractor...")
        sys.exit(0)

if __name__ == "__main__":
    main()
