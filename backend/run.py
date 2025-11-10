#!/usr/bin/env python3
"""
OCRD Extractor - Modern FastAPI Backend
Run this script to start the server
"""

import uvicorn
import os
import sys
from pathlib import Path

# Add the app directory to Python path
app_dir = Path(__file__).parent / "app"
sys.path.insert(0, str(app_dir))

if __name__ == "__main__":
    # Use plain text to avoid encoding issues on Windows
    print("Starting OCRD Extractor API...")
    print("Modern document analysis with multiple LLM providers")
    print("Server will be available at: http://localhost:8000")
    print("API docs available at: http://localhost:8000/docs")
    print("=" * 50)
    
    # Get host and port from environment variables (for Render deployment)
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    reload = os.getenv("DEBUG", "False").lower() == "true"
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
