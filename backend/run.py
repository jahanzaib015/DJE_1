#!/usr/bin/env python3
"""
OCRD Extractor - Modern FastAPI Backend
Run this script to start the server
"""

import uvicorn
import os
import sys
import subprocess
import time
from pathlib import Path

# Add the app directory to Python path
app_dir = Path(__file__).parent / "app"
sys.path.insert(0, str(app_dir))

def check_and_cleanup_logs():
    """Check for locked log files and attempt cleanup"""
    logs_dir = Path(__file__).parent.parent / "logs"
    if not logs_dir.exists():
        return
    
    log_files = [
        logs_dir / "app.log",
        logs_dir / "error.log",
        logs_dir / "requests.log"
    ]
    
    locked_files = []
    for log_file in log_files:
        if log_file.exists():
            try:
                # Try to open in append mode to check if locked
                with open(log_file, 'a', encoding='utf-8') as f:
                    pass
            except (PermissionError, IOError, OSError):
                locked_files.append(log_file)
                print(f"⚠️  Warning: Log file {log_file.name} appears to be locked")
    
    if locked_files:
        print("💡 Tip: If you see errors, try closing other Python processes or restarting your computer")
        print("   The app will continue with console logging only for locked files")

def check_port_availability(host: str, port: int) -> bool:
    """Check if a port is available by attempting to bind to it on the specified host"""
    try:
        import socket
        # Try to bind to the port on the same host that will be used - if successful, port is available
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
            return True
    except OSError:
        # Port is in use or unavailable
        return False
    except Exception:
        # For any other exception, assume available (better to try than fail)
        return True

if __name__ == "__main__":
    # Use plain text to avoid encoding issues on Windows
    print("=" * 60)
    print("🚀 Starting OCRD Extractor API...")
    print("   Modern document analysis with multiple LLM providers")
    print("=" * 60)
    print()
    
    # Check for locked log files
    print("[1/4] Checking log files...")
    check_and_cleanup_logs()
    print("   ✅ Log check complete")
    print()
    
    # Get host and port from environment variables (for Render deployment)
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    # Disable reload by default for production (enable in development by setting DEBUG=true)
    # Render sets DEBUG=False, so reload will be disabled in production
    reload = os.getenv("DEBUG", "False").lower() == "true"
    
    # Check port availability
    print(f"[2/4] Checking port {port}...")
    if not check_port_availability(host, port):
        print(f"   ⚠️  Warning: Port {port} appears to be in use on {host}")
        print(f"   💡 Tip: Run 'kill_port_8000.bat' to free the port, or use a different port")
        print(f"   Continuing anyway... (may fail if port is truly occupied)")
    else:
        print(f"   ✅ Port {port} is available on {host}")
    print()
    
    print(f"[3/4] Server configuration:")
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    print(f"   Reload: {reload}")
    print()
    
    print(f"[4/4] Starting server...")
    print(f"   Server will be available at: http://localhost:{port}")
    print(f"   API docs available at: http://localhost:{port}/docs")
    print("=" * 60)
    print()
    
    try:
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port,
            reload=reload,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error starting server: {e}")
        print("\n💡 Troubleshooting tips:")
        print("   1. Check if port is already in use: netstat -ano | findstr :8000")
        print("   2. Kill stale processes: kill_port_8000.bat")
        print("   3. Check log files in backend/logs/ for details")
        print("   4. Try restarting your computer if file locks persist")
        sys.exit(1)
