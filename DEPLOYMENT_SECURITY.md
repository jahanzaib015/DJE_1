# 🔒 Safe Deployment Guide

## ⚠️ **CRITICAL: Never Commit API Keys to GitHub!**

### 🚨 What NOT to do:
- ❌ Never put real API keys in `.env` files that go to GitHub
- ❌ Never hardcode API keys in your code
- ❌ Never commit `.env` files to version control

### ✅ What TO do:

## 1. **Local Development (Safe)**

### Set up your local environment:
```bash
# 1. Copy template files
cp backend/env.template backend/.env
cp env.template .env
cp frontend/env.template frontend/.env

# 2. Edit the .env files and add your REAL API key
# Edit backend/.env - replace 'your_openai_api_key_here' with your actual key
# Edit .env - replace 'your_openai_api_key_here' with your actual key

# 3. Test locally
py check_environment.py
py run_nodejs.py
```

## 2. **GitHub Repository (Safe)**

### What gets committed to GitHub:
- ✅ `env.template` files (with placeholder values)
- ✅ `.gitignore` (protects `.env` files)
- ✅ All source code
- ✅ Configuration files
- ❌ **NO** `.env` files with real keys
- ❌ **NO** API keys anywhere

### Verify before pushing:
```bash
# Check what will be committed
git status

# Make sure .env files are ignored
git check-ignore backend/.env
git check-ignore .env
git check-ignore frontend/.env
```

## 3. **Render Deployment (Safe)**

### For Render deployment, you'll set environment variables in the Render dashboard:

#### Backend Service Environment Variables:
```
OPENAI_API_KEY=your_actual_api_key_here
HOST=0.0.0.0
PORT=8000
DEBUG=False
MAX_FILE_SIZE=50MB
UPLOAD_DIR=uploads
EXPORT_DIR=exports
DEFAULT_LLM_PROVIDER=openai
DEFAULT_MODEL=gpt-4
DEFAULT_ANALYSIS_METHOD=llm
FRONTEND_URL=https://your-frontend-url.onrender.com
```

#### Frontend Service Environment Variables:
```
REACT_APP_API_URL=https://your-backend-url.onrender.com
```

### How to set environment variables in Render:
1. Go to your Render dashboard
2. Select your service
3. Go to "Environment" tab
4. Add each variable with its value
5. Deploy

## 4. **Current Project Status**

### ✅ Safe for GitHub:
- All `.env` files are in `.gitignore`
- Template files have placeholder values
- No real API keys in the codebase

### 🔧 What you need to do:

#### For Local Development:
1. **Set your API key locally:**
   ```bash
   # Edit these files and add your real API key:
   # - backend/.env
   # - .env
   ```

2. **Test locally:**
   ```bash
   py check_environment.py
   py run_nodejs.py
   ```

#### For GitHub Push:
1. **Verify .env files are ignored:**
   ```bash
   git status
   # Should NOT show .env files
   ```

2. **Push to GitHub:**
   ```bash
   git add .
   git commit -m "Add OCRD Extractor with environment setup"
   git push origin main
   ```

#### For Render Deployment:
1. **Connect GitHub to Render**
2. **Set environment variables in Render dashboard** (not in code)
3. **Deploy**

## 5. **Security Best Practices**

### ✅ Do:
- Use environment variables for all secrets
- Keep `.env` files in `.gitignore`
- Use template files for documentation
- Set environment variables in deployment platforms
- Rotate API keys regularly

### ❌ Don't:
- Commit `.env` files
- Hardcode API keys
- Share API keys in chat/email
- Use the same key for development and production

## 6. **Verification Commands**

### Check what's safe to commit:
```bash
# Check git status (should not show .env files)
git status

# Check if .env files are ignored
git check-ignore backend/.env .env frontend/.env

# Verify template files exist
ls -la backend/env.template env.template frontend/env.template
```

### Test environment setup:
```bash
# Check environment (will show API key error until you set it)
py check_environment.py

# After setting API key, this should pass
py check_environment.py
```

## 🎯 **Next Steps**

1. **Set your API key locally** (in `.env` files)
2. **Test the application** locally
3. **Verify .env files are ignored** by git
4. **Push to GitHub** (safely)
5. **Deploy to Render** (using environment variables)

Your project is now set up securely for GitHub and Render deployment! 🚀
