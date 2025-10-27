#!/usr/bin/env python3
"""
Secure API key setup script for OCRD Extractor.
This script helps you set up your OpenAI API key without exposing it in code.
"""

import os
import sys

def setup_api_key_securely():
    print("Secure OpenAI API Key Setup")
    print("=" * 40)
    print()
    print("This script will help you set up your OpenAI API key securely.")
    print("Your API key will NOT be committed to GitHub.")
    print()
    print("Steps:")
    print("1. Get your API key from: https://platform.openai.com/api-keys")
    print("2. Choose how to set it up:")
    print("   a) System environment variable (recommended)")
    print("   b) Local .env file (for development only)")
    print()
    
    choice = input("Choose option (a or b): ").strip().lower()
    
    if choice == 'a':
        return setup_system_env_var()
    elif choice == 'b':
        return setup_local_env_file()
    else:
        print("Invalid choice. Exiting.")
        return False

def setup_system_env_var():
    print()
    print("Setting up system environment variable...")
    print()
    print("For Windows PowerShell, run this command:")
    print('$env:OPENAI_API_KEY="your_actual_api_key_here"')
    print()
    print("For Windows Command Prompt, run this command:")
    print('set OPENAI_API_KEY=your_actual_api_key_here')
    print()
    print("For permanent setup, add it to your system environment variables:")
    print("1. Open System Properties > Environment Variables")
    print("2. Add OPENAI_API_KEY with your actual API key")
    print()
    print("After setting the environment variable, restart your terminal and application.")
    return True

def setup_local_env_file():
    print()
    print("Setting up local .env file...")
    print("WARNING: This is for development only. Never commit .env files!")
    print()
    
    api_key = input("Enter your OpenAI API key: ").strip()
    
    if not api_key or api_key == "your_openai_api_key_here":
        print("Invalid API key. Exiting.")
        return False
    
    try:
        # Read current .env file
        with open('.env', 'r') as f:
            content = f.read()
        
        # Replace the placeholder
        updated_content = content.replace(
            "OPENAI_API_KEY=your_openai_api_key_here", 
            f"OPENAI_API_KEY={api_key}"
        )
        
        # Write back to .env file
        with open('.env', 'w') as f:
            f.write(updated_content)
        
        print(f"✅ API key saved to .env file: {api_key[:8]}...")
        print("⚠️  Remember: Never commit .env files to GitHub!")
        return True
        
    except Exception as e:
        print(f"❌ Error updating .env file: {e}")
        return False

if __name__ == "__main__":
    if setup_api_key_securely():
        print()
        print("🚀 Setup complete! You can now start your application.")
        print("Run: py run.py (for backend) or node server.js (for frontend)")
    else:
        print("❌ Setup failed. Please try again.")
        sys.exit(1)

