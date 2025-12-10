#!/usr/bin/env python3
"""
Setup script for local deployment environment
Creates necessary .env files and directories
"""

import os
from pathlib import Path

def create_env_file(file_path, content):
    """Create .env file if it doesn't exist"""
    env_path = Path(file_path)
    if env_path.exists():
        print(f"⚠️  {file_path} already exists, skipping...")
        return False
    
    env_path.parent.mkdir(parents=True, exist_ok=True)
    with open(env_path, 'w') as f:
        f.write(content)
    print(f"✅ Created {file_path}")
    return True

def create_directories():
    """Create necessary directories"""
    dirs = [
        "backend/uploads",
        "backend/exports",
        "backend/logs",
        "uploads",
        "exports",
        "traces"
    ]
    
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"✅ Created directory: {dir_path}")

def main():
    print("=" * 50)
    print("  OCRD Extractor - Local Environment Setup")
    print("=" * 50)
    print()
    
    # Backend .env content
    backend_env = """# OpenAI API Configuration
# Add your OpenAI API key here (optional, for ChatGPT integration)
OPENAI_API_KEY=your_openai_api_key_here

# Server Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=True

# File Upload Configuration
MAX_FILE_SIZE=50MB
UPLOAD_DIR=uploads
EXPORT_DIR=exports

# LLM Configuration
DEFAULT_LLM_PROVIDER=openai
DEFAULT_MODEL=gpt-4
DEFAULT_ANALYSIS_METHOD=llm_with_fallback
"""
    
    # Frontend .env content
    frontend_env = """# React App Configuration
# Use localhost for local development
REACT_APP_API_URL=http://localhost:8000
REACT_APP_WS_URL=ws://localhost:8000

# Development Configuration
PORT=3000
"""
    
    # Root .env content (for Node.js server)
    root_env = """# Node.js Server Configuration
PORT=3000
NODE_ENV=development
PYTHON_BACKEND_URL=http://localhost:8000
"""
    
    print("📝 Creating environment files...")
    create_env_file("backend/.env", backend_env)
    create_env_file("frontend/.env", frontend_env)
    create_env_file(".env", root_env)
    
    print()
    print("📁 Creating necessary directories...")
    create_directories()
    
    print()
    print("=" * 50)
    print("✅ Environment setup complete!")
    print("=" * 50)
    print()
    print("📋 Next steps:")
    print("1. Edit backend/.env and add your OpenAI API key (optional)")
    print("2. Install dependencies:")
    print("   - Python: pip install -r backend/requirements.txt")
    print("   - Node.js: npm install && cd frontend && npm install")
    print("3. Start the application:")
    print("   - Windows: start_local.bat")
    print("   - macOS/Linux: ./start_local.sh")
    print()
    print("🌐 Once running:")
    print("   - Frontend: http://localhost:3000")
    print("   - Backend API: http://localhost:8000")
    print("   - API Docs: http://localhost:8000/docs")
    print()

if __name__ == "__main__":
    main()






