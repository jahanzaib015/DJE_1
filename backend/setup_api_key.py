#!/usr/bin/env python3
"""
Simple script to set up OpenAI API key for the OCRD Extractor backend.
"""

import os
import sys

def setup_api_key():
    print("🔑 OpenAI API Key Setup for OCRD Extractor")
    print("=" * 50)
    
    # Check if API key is already set
    current_key = os.getenv("OPENAI_API_KEY")
    if current_key and current_key != "your_openai_api_key_here":
        print(f"✅ API key is already set: {current_key[:8]}...")
        return True
    
    print("Please enter your OpenAI API key:")
    print("(You can get one from: https://platform.openai.com/api-keys)")
    print()
    
    api_key = input("OpenAI API Key: ").strip()
    
    if not api_key:
        print("❌ No API key provided. Exiting.")
        return False
    
    if api_key == "your_openai_api_key_here":
        print("❌ Please enter your actual API key, not the placeholder.")
        return False
    
    # Set environment variable for current session
    os.environ["OPENAI_API_KEY"] = api_key
    
    print(f"✅ API key set for current session: {api_key[:8]}...")
    print()
    print("📝 To make this permanent, you can:")
    print("1. Set it as a system environment variable")
    print("2. Create a .env file in the backend directory")
    print("3. Run this script each time you start the application")
    print()
    
    return True

if __name__ == "__main__":
    if setup_api_key():
        print("🚀 You can now start the backend server!")
        print("Run: python run.py")
    else:
        print("❌ Setup failed. Please try again.")
        sys.exit(1)
