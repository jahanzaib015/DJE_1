#!/usr/bin/env python3
"""
OCRD Extractor - Render Deployment Helper Script
This script helps prepare your application for Render deployment
"""

import os
import sys
import subprocess
from pathlib import Path

def check_requirements():
    """Check if all required files exist"""
    required_files = [
        "backend/requirements.txt",
        "backend/run.py",
        "frontend/package.json",
        "frontend/src/services/AnalysisService.ts"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Missing required files:")
        for file_path in missing_files:
            print(f"   - {file_path}")
        return False
    
    print("✅ All required files found")
    return True

def check_environment_variables():
    """Check if environment variables are properly configured"""
    print("\n📋 Environment Variables Checklist:")
    print("Backend Environment Variables:")
    backend_vars = [
        "OPENAI_API_KEY",
        "HOST",
        "PORT", 
        "DEBUG",
        "MAX_FILE_SIZE",
        "UPLOAD_DIR",
        "EXPORT_DIR",
        "DEFAULT_LLM_PROVIDER",
        "DEFAULT_MODEL",
        "DEFAULT_ANALYSIS_METHOD"
    ]
    
    for var in backend_vars:
        print(f"   ✓ {var}")
    
    print("\nFrontend Environment Variables:")
    frontend_vars = ["REACT_APP_API_URL"]
    for var in frontend_vars:
        print(f"   ✓ {var}")
    
    print("\n⚠️  Remember to set these in your Render dashboard!")

def show_deployment_steps():
    """Show step-by-step deployment instructions"""
    print("\n🚀 Render Deployment Steps:")
    print("\n1. Backend Deployment:")
    print("   - Go to Render dashboard")
    print("   - Click 'New +' → 'Web Service'")
    print("   - Connect your GitHub repository")
    print("   - Configure:")
    print("     • Name: ocrd-extractor-backend")
    print("     • Environment: Python 3")
    print("     • Build Command: pip install --upgrade pip && pip install -r backend/requirements.txt")
    print("     • Start Command: cd backend && python run.py")
    print("     • Python Version: 3.11.0")
    print("   - Set environment variables (see checklist above)")
    print("   - Deploy and note the backend URL")
    
    print("\n2. Frontend Deployment:")
    print("   - Go to Render dashboard")
    print("   - Click 'New +' → 'Static Site'")
    print("   - Connect your GitHub repository")
    print("   - Configure:")
    print("     • Name: ocrd-extractor-frontend")
    print("     • Build Command: cd frontend && npm install && npm run build")
    print("     • Publish Directory: frontend/build")
    print("   - Set REACT_APP_API_URL to your backend URL")
    print("   - Deploy and note the frontend URL")
    
    print("\n3. Update Backend CORS:")
    print("   - Add FRONTEND_URL environment variable to backend")
    print("   - Redeploy backend service")
    
    print("\n4. Test Deployment:")
    print("   - Visit your frontend URL")
    print("   - Test file upload and analysis")
    print("   - Check backend logs for any errors")

def main():
    """Main deployment helper function"""
    print("🔧 OCRD Extractor - Render Deployment Helper")
    print("=" * 50)
    
    # Check if we're in the right directory
    if not Path("backend").exists() or not Path("frontend").exists():
        print("❌ Please run this script from the project root directory")
        sys.exit(1)
    
    # Check requirements
    if not check_requirements():
        print("\n❌ Please ensure all required files exist before deploying")
        sys.exit(1)
    
    # Show environment variables checklist
    check_environment_variables()
    
    # Show deployment steps
    show_deployment_steps()
    
    print("\n📚 For detailed instructions, see RENDER_DEPLOYMENT.md")
    print("\n✅ Your application is ready for Render deployment!")

if __name__ == "__main__":
    main()
