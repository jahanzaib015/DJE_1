#!/usr/bin/env python3
"""
Simple Environment Setup Script for OCRD Extractor
This script creates all necessary environment files and directories without requiring user input.
"""

import os
from pathlib import Path

def create_env_file(file_path, content):
    """Create an environment file with the given content"""
    try:
        with open(file_path, 'w') as f:
            f.write(content)
        print(f"SUCCESS: Created {file_path}")
        return True
    except Exception as e:
        print(f"ERROR: Failed to create {file_path}: {e}")
        return False

def setup_directories():
    """Create necessary directories"""
    directories = ["uploads", "exports", "backend/uploads", "backend/exports"]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"SUCCESS: Created directory: {directory}")

def main():
    """Main setup function"""
    print("OCRD Extractor Environment Setup (Simple)")
    print("=" * 50)
    print("Creating environment files and directories...")
    print()
    
    # Create directories
    print("Creating directories...")
    setup_directories()
    print()
    
    # Backend environment file
    backend_env_content = """# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Server Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=True

# File Upload Configuration
MAX_FILE_SIZE=50MB
UPLOAD_DIR=uploads
EXPORT_DIR=exports

# LLM Configuration (OpenAI only)
DEFAULT_LLM_PROVIDER=openai
DEFAULT_MODEL=gpt-4
DEFAULT_ANALYSIS_METHOD=llm

# CORS Configuration (for frontend)
FRONTEND_URL=http://localhost:3000
"""
    
    # Root environment file
    root_env_content = backend_env_content
    
    # Frontend environment file
    frontend_env_content = """# React App Configuration
REACT_APP_API_URL=http://localhost:3000
REACT_APP_WS_URL=ws://localhost:8080

# Development Configuration
PORT=3000
"""
    
    # Create environment files
    print("Creating environment files...")
    backend_success = create_env_file("backend/.env", backend_env_content)
    root_success = create_env_file(".env", root_env_content)
    frontend_success = create_env_file("frontend/.env", frontend_env_content)
    
    print()
    
    if backend_success and root_success and frontend_success:
        print("Environment setup complete!")
        print()
        print("IMPORTANT: You need to set your OpenAI API key:")
        print("1. Edit backend/.env and replace 'your_openai_api_key_here' with your actual API key")
        print("2. Edit .env and replace 'your_openai_api_key_here' with your actual API key")
        print("3. Get your API key from: https://platform.openai.com/api-keys")
        print()
        print("Next steps:")
        print("1. Set your OpenAI API key in the .env files")
        print("2. Run: python check_environment.py (to verify setup)")
        print("3. Run: python run_nodejs.py (to start the application)")
        print("   Or: start_nodejs.bat (Windows)")
        return True
    else:
        print("ERROR: Some environment files could not be created.")
        return False

if __name__ == "__main__":
    try:
        success = main()
        if not success:
            exit(1)
    except Exception as e:
        print(f"ERROR: Setup failed: {e}")
        exit(1)
