#!/usr/bin/env python3
"""
Simple script to set up OpenAI API key for the OCRD Extractor backend.
"""

import os
import sys

def setup_api_key():
    print("OpenAI API Key Setup for OCRD Extractor")
    print("=" * 50)
    
    # Check if API key is already set
    current_key = os.getenv("OPENAI_API_KEY")
    if current_key and current_key != "your_openai_api_key_here":
        print(f"API key is already set: {current_key[:8]}...")
        return True
    
    print("Please enter your OpenAI API key:")
    print("(You can get one from: https://platform.openai.com/api-keys)")
    print()
    
    api_key = input("OpenAI API Key: ").strip()
    
    if not api_key:
        print("No API key provided. Exiting.")
        return False
    
    if api_key == "your_openai_api_key_here":
        print("Please enter your actual API key, not the placeholder.")
        return False
    
    # Update the .env file
    env_file = ".env"
    try:
        with open(env_file, 'r') as f:
            content = f.read()
        
        # Replace the placeholder with the actual API key
        updated_content = content.replace("OPENAI_API_KEY=your_openai_api_key_here", f"OPENAI_API_KEY={api_key}")
        
        with open(env_file, 'w') as f:
            f.write(updated_content)
        
        print(f"API key saved to .env file: {api_key[:8]}...")
        print()
        print("The API key has been saved to your .env file.")
        print("You can now restart your application to use the new API key.")
        print()
        
        return True
        
    except Exception as e:
        print(f"Error updating .env file: {e}")
        return False

if __name__ == "__main__":
    if setup_api_key():
        print("You can now start the backend server!")
        print("Run: py run.py")
    else:
        print("Setup failed. Please try again.")
        sys.exit(1)

