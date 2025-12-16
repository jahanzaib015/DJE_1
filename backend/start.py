#!/usr/bin/env python3
"""
Startup script for Render deployment
Ensures proper port binding and error handling
"""
import os
import sys
import subprocess

def main():
    # Get port from environment (Render sets this)
    port = os.getenv("PORT", "8000")
    host = os.getenv("HOST", "0.0.0.0")
    
    # Ensure we're in the backend directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Set PYTHONPATH
    pythonpath = os.getenv("PYTHONPATH", "")
    if script_dir not in pythonpath:
        os.environ["PYTHONPATH"] = f"{script_dir}:{pythonpath}" if pythonpath else script_dir
    
    print("=== Starting OCRD Extractor Backend ===", flush=True)
    print(f"PORT: {port}", flush=True)
    print(f"HOST: {host}", flush=True)
    print(f"Working directory: {os.getcwd()}", flush=True)
    print(f"Python version: {sys.version}", flush=True)
    print("", flush=True)
    
    # Validate port
    try:
        port_int = int(port)
        if port_int < 1 or port_int > 65535:
            raise ValueError(f"Port {port_int} is out of range")
    except ValueError as e:
        print(f"ERROR: Invalid PORT: {e}", flush=True)
        sys.exit(1)
    
    # Test import (but don't fail if it's slow - just log)
    print("Testing app import...", flush=True)
    try:
        from app.main import app
        print("✅ App imported successfully", flush=True)
    except Exception as e:
        print(f"ERROR: Failed to import app: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("", flush=True)
    print(f"Starting uvicorn on {host}:{port}...", flush=True)
    print("⚠️  IMPORTANT: Server must bind to port within 60 seconds for Render", flush=True)
    print("", flush=True)
    
    # Start uvicorn with minimal configuration for fastest startup
    try:
        import uvicorn
        # Use minimal config to ensure fastest possible startup
        # access_log=False reduces overhead
        # log_level="warning" reduces logging overhead during startup
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port_int,
            log_level="warning",  # Reduced logging for faster startup
            timeout_keep_alive=30,
            access_log=False,
            # Don't wait for workers or other delays
            loop="auto"  # Let uvicorn choose the fastest loop
        )
    except KeyboardInterrupt:
        print("\nServer stopped by user", flush=True)
        sys.exit(0)
    except Exception as e:
        print(f"\nERROR: Failed to start server: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

