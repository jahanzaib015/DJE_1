#!/usr/bin/env python3
"""
OCRD Extractor - Cross-platform Installation Script
This script handles the installation process for Windows, macOS, and Linux
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

def run_command(command, description, check=True):
    """Run a command and handle errors"""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=check, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {description} completed")
            return True
        else:
            print(f"❌ {description} failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ {description} failed: {str(e)}")
        return False

def check_python():
    """Check if Python is available"""
    print("🐍 Checking Python installation...")
    try:
        result = subprocess.run([sys.executable, "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Python found: {result.stdout.strip()}")
            return True
        else:
            print("❌ Python not found")
            return False
    except Exception as e:
        print(f"❌ Python check failed: {str(e)}")
        return False

def create_venv():
    """Create virtual environment"""
    venv_path = Path("venv")
    if venv_path.exists():
        print("✅ Virtual environment already exists")
        return True
    
    return run_command(
        f"{sys.executable} -m venv venv",
        "Creating virtual environment"
    )

def get_activate_command():
    """Get the correct activation command for the platform"""
    system = platform.system().lower()
    if system == "windows":
        return "venv\\Scripts\\activate"
    else:
        return "source venv/bin/activate"

def install_dependencies():
    """Install all dependencies"""
    # Get activation command
    activate_cmd = get_activate_command()
    
    # Upgrade pip first
    if not run_command(
        f"{activate_cmd} && python -m pip install --upgrade pip",
        "Upgrading pip"
    ):
        return False
    
    # Install backend dependencies
    print("\n📦 Installing backend dependencies...")
    backend_success = run_command(
        f"{activate_cmd} && pip install --no-cache-dir -r backend/requirements_simple.txt",
        "Installing backend dependencies"
    )
    
    # If backend installation fails, try with binary-only packages
    if not backend_success:
        print("🔄 Trying alternative installation method...")
        backend_success = run_command(
            f"{activate_cmd} && pip install --no-cache-dir --only-binary=all -r backend/requirements_simple.txt",
            "Installing backend dependencies (binary only)"
        )
    
    if not backend_success:
        return False
    
    # Install frontend dependencies
    print("\n📦 Installing frontend dependencies...")
    if not run_command(
        f"{activate_cmd} && pip install --no-cache-dir -r requirements.txt",
        "Installing frontend dependencies"
    ):
        return False
    
    return True

def start_server():
    """Start the OCRD Extractor server"""
    activate_cmd = get_activate_command()
    
    print("\n🚀 Starting OCRD Extractor...")
    print("📄 Main app: http://localhost:8000")
    print("📚 API docs: http://localhost:8000/docs")
    print("=" * 50)
    
    # Change to backend directory and start server
    os.chdir("backend")
    try:
        subprocess.run(f"{activate_cmd} && python run.py", shell=True, check=True)
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"❌ Failed to start server: {str(e)}")

def main():
    """Main installation process"""
    print("🚀 OCRD Extractor - Installation Script")
    print("=" * 50)
    
    # Check Python
    if not check_python():
        print("\n❌ Python is required but not found.")
        print("Please install Python 3.8+ from https://python.org")
        sys.exit(1)
    
    # Create virtual environment
    if not create_venv():
        print("\n❌ Failed to create virtual environment")
        sys.exit(1)
    
    # Install dependencies
    if not install_dependencies():
        print("\n❌ Failed to install dependencies")
        print("\n💡 Troubleshooting tips:")
        print("1. Make sure you have a stable internet connection")
        print("2. Try running: pip install --upgrade pip")
        print("3. On Windows, you might need Visual Studio Build Tools")
        print("4. Try: pip install --only-binary=all -r backend/requirements_simple.txt")
        sys.exit(1)
    
    print("\n✅ Installation completed successfully!")
    
    # Ask if user wants to start the server
    try:
        start_now = input("\n🚀 Start the server now? (y/n): ").lower().strip()
        if start_now in ['y', 'yes', '']:
            start_server()
        else:
            print("\n📝 To start the server manually:")
            print(f"   {get_activate_command()}")
            print("   cd backend")
            print("   python run.py")
    except KeyboardInterrupt:
        print("\n👋 Installation cancelled by user")

if __name__ == "__main__":
    main()
