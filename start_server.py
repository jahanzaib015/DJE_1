#!/usr/bin/env python3
"""
Quick start script for OCRD Extractor
"""

import subprocess
import sys
import os
from pathlib import Path

def main():
    print("🚀 OCRD Extractor - Modern API")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not Path("backend").exists():
        print("❌ Error: Please run this script from the project root directory")
        print("   The 'backend' folder should be in the current directory")
        sys.exit(1)
    
    # Change to backend directory
    os.chdir("backend")
    
    # Check if requirements are installed
    try:
        import fastapi
        print("✅ FastAPI is installed")
    except ImportError:
        print("📦 Installing dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    
    # Start the server
    print("\n🌐 Starting server...")
    print("📄 Main app: http://localhost:8000")
    print("📚 API docs: http://localhost:8000/docs")
    print("=" * 40)
    
    try:
        subprocess.run([sys.executable, "run.py"])
    except KeyboardInterrupt:
        print("\n👋 Server stopped")

if __name__ == "__main__":
    main()
