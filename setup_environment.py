#!/usr/bin/env python3
"""
Environment Setup Script for OCRD Extractor
This script helps you set up all necessary environment variables and configuration files.
"""

import os
import sys
import shutil
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

def setup_backend_env():
    """Set up backend environment file"""
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
    
    backend_path = Path("backend/.env")
    return create_env_file(backend_path, backend_env_content)

def setup_root_env():
    """Set up root environment file"""
    root_env_content = """# OpenAI API Configuration
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
    
    root_path = Path(".env")
    return create_env_file(root_path, root_env_content)

def setup_frontend_env():
    """Set up frontend environment file"""
    frontend_env_content = """# React App Configuration
REACT_APP_API_URL=http://localhost:3000
REACT_APP_WS_URL=ws://localhost:8080

# Development Configuration
PORT=3000
"""
    
    frontend_path = Path("frontend/.env")
    return create_env_file(frontend_path, frontend_env_content)

def setup_directories():
    """Create necessary directories"""
    directories = ["uploads", "exports", "backend/uploads", "backend/exports"]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"SUCCESS: Created directory: {directory}")

def get_api_key():
    """Get OpenAI API key from user"""
    print("\nOpenAI API Key Setup")
    print("=" * 40)
    print("You need an OpenAI API key to use this application.")
    print("Get one from: https://platform.openai.com/api-keys")
    print()
    
    api_key = input("Enter your OpenAI API key: ").strip()
    
    if not api_key or api_key == "your_openai_api_key_here":
        print("ERROR: Invalid API key. Please try again.")
        return None
    
    return api_key

def update_env_files_with_api_key(api_key):
    """Update all .env files with the actual API key"""
    env_files = [
        "backend/.env",
        ".env"
    ]
    
    for env_file in env_files:
        if Path(env_file).exists():
            try:
                with open(env_file, 'r') as f:
                    content = f.read()
                
                updated_content = content.replace("your_openai_api_key_here", api_key)
                
                with open(env_file, 'w') as f:
                    f.write(updated_content)
                
                print(f"SUCCESS: Updated {env_file} with API key")
            except Exception as e:
                print(f"ERROR: Failed to update {env_file}: {e}")

def main():
    """Main setup function"""
    print("OCRD Extractor Environment Setup")
    print("=" * 50)
    print("This script will set up all necessary environment files and directories.")
    print()
    
    # Create directories
    print("Creating directories...")
    setup_directories()
    print()
    
    # Create environment files
    print("Creating environment files...")
    backend_success = setup_backend_env()
    root_success = setup_root_env()
    frontend_success = setup_frontend_env()
    print()
    
    if not (backend_success and root_success and frontend_success):
        print("ERROR: Some environment files could not be created.")
        return False
    
    # Get API key from user
    api_key = get_api_key()
    if api_key:
        print("\nUpdating environment files with API key...")
        update_env_files_with_api_key(api_key)
        print()
    
    # Final instructions
    print("Environment setup complete!")
    print()
    print("Next steps:")
    print("1. Verify your API key is set correctly in the .env files")
    print("2. Run the application:")
    print("   - For Python backend: cd backend && python run.py")
    print("   - For Node.js frontend: python run_nodejs.py")
    print("   - Or use: start_nodejs.bat (Windows)")
    print()
    print("Access points:")
    print("   - Frontend: http://localhost:3000")
    print("   - Backend API: http://localhost:8000")
    print("   - API Docs: http://localhost:8000/docs")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nERROR: Setup cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: Setup failed: {e}")
        sys.exit(1)