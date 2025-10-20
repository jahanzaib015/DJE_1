#!/usr/bin/env python3
"""
Environment Check Script for OCRD Extractor
This script validates that all environment variables and configurations are set correctly.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def check_env_file(file_path):
    """Check if environment file exists and has required variables"""
    if not Path(file_path).exists():
        return False, f"File {file_path} does not exist"
    
    load_dotenv(file_path)
    
    required_vars = [
        "OPENAI_API_KEY",
        "HOST",
        "PORT",
        "DEFAULT_LLM_PROVIDER",
        "DEFAULT_MODEL"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        return False, f"Missing variables: {', '.join(missing_vars)}"
    
    return True, "All required variables present"

def check_api_key():
    """Check if OpenAI API key is properly configured"""
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        return False, "OPENAI_API_KEY not set"
    
    if api_key == "your_openai_api_key_here":
        return False, "OPENAI_API_KEY is still the placeholder value"
    
    if not api_key.startswith("sk-"):
        return False, "OPENAI_API_KEY doesn't look like a valid OpenAI key"
    
    return True, f"API key configured: {api_key[:8]}..."

def check_directories():
    """Check if required directories exist"""
    required_dirs = [
        "uploads",
        "exports",
        "backend/uploads",
        "backend/exports"
    ]
    
    missing_dirs = []
    for directory in required_dirs:
        if not Path(directory).exists():
            missing_dirs.append(directory)
    
    if missing_dirs:
        return False, f"Missing directories: {', '.join(missing_dirs)}"
    
    return True, "All required directories exist"

def check_python_dependencies():
    """Check if Python dependencies are installed"""
    try:
        import fastapi
        import uvicorn
        import openai
        import pandas
        import openpyxl
        return True, "All Python dependencies available"
    except ImportError as e:
        return False, f"Missing Python dependency: {e}"

def check_node_dependencies():
    """Check if Node.js dependencies are installed"""
    node_modules = Path("node_modules")
    frontend_node_modules = Path("frontend/node_modules")
    
    if not node_modules.exists():
        return False, "Node.js dependencies not installed (run: npm install)"
    
    if not frontend_node_modules.exists():
        return False, "Frontend dependencies not installed (run: cd frontend && npm install)"
    
    return True, "All Node.js dependencies available"

def main():
    """Main environment check function"""
    print("OCRD Extractor Environment Check")
    print("=" * 50)
    
    all_checks_passed = True
    
    # Check environment files
    print("\nChecking environment files...")
    env_files = [
        ("backend/.env", "Backend environment"),
        (".env", "Root environment"),
        ("frontend/.env", "Frontend environment")
    ]
    
    for env_file, description in env_files:
        success, message = check_env_file(env_file)
        if success:
            print(f"SUCCESS: {description}: {message}")
        else:
            print(f"ERROR: {description}: {message}")
            all_checks_passed = False
    
    # Check API key
    print("\nChecking OpenAI API key...")
    success, message = check_api_key()
    if success:
        print(f"SUCCESS: {message}")
    else:
        print(f"ERROR: {message}")
        all_checks_passed = False
    
    # Check directories
    print("\nChecking directories...")
    success, message = check_directories()
    if success:
        print(f"SUCCESS: {message}")
    else:
        print(f"ERROR: {message}")
        all_checks_passed = False
    
    # Check Python dependencies
    print("\nChecking Python dependencies...")
    success, message = check_python_dependencies()
    if success:
        print(f"SUCCESS: {message}")
    else:
        print(f"ERROR: {message}")
        all_checks_passed = False
    
    # Check Node.js dependencies
    print("\nChecking Node.js dependencies...")
    success, message = check_node_dependencies()
    if success:
        print(f"SUCCESS: {message}")
    else:
        print(f"ERROR: {message}")
        all_checks_passed = False
    
    # Final result
    print("\n" + "=" * 50)
    if all_checks_passed:
        print("All environment checks passed!")
        print("\nYou can now start the application:")
        print("   - Backend: cd backend && python run.py")
        print("   - Full app: python run_nodejs.py")
        print("   - Windows: start_nodejs.bat")
    else:
        print("Some environment checks failed.")
        print("\nPlease fix the issues above and run this script again.")
        print("   Or run: python setup_environment.py")
    
    return all_checks_passed

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nERROR: Check cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: Check failed: {e}")
        sys.exit(1)
