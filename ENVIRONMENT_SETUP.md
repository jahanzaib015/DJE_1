# 🔧 Environment Setup Guide

This guide will help you set up the OCRD Extractor with OpenAI API integration.

## 🚀 Quick Setup (Recommended)

### For Windows Users:
```bash
# Run the automated setup
setup_env.bat
```

### For All Platforms:
```bash
# Run the Python setup script
python setup_environment.py

# Check your setup
python check_environment.py
```

## 📋 Manual Setup

### Step 1: Get OpenAI API Key

1. Go to [OpenAI Platform](https://platform.openai.com/api-keys)
2. Sign in or create an account
3. Click "Create new secret key"
4. Copy the API key (starts with `sk-`)

### Step 2: Create Environment Files

#### Backend Environment (`backend/.env`):
```env
# OpenAI API Configuration
OPENAI_API_KEY=your_actual_api_key_here

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
```

#### Root Environment (`.env`):
```env
# Same content as backend/.env
OPENAI_API_KEY=your_actual_api_key_here
HOST=0.0.0.0
PORT=8000
DEBUG=True
MAX_FILE_SIZE=50MB
UPLOAD_DIR=uploads
EXPORT_DIR=exports
DEFAULT_LLM_PROVIDER=openai
DEFAULT_MODEL=gpt-4
DEFAULT_ANALYSIS_METHOD=llm
FRONTEND_URL=http://localhost:3000
```

#### Frontend Environment (`frontend/.env`):
```env
# React App Configuration
REACT_APP_API_URL=http://localhost:3000
REACT_APP_WS_URL=ws://localhost:8080

# Development Configuration
PORT=3000
```

### Step 3: Create Required Directories

```bash
# Create upload and export directories
mkdir uploads exports
mkdir backend/uploads backend/exports
```

### Step 4: Install Dependencies

#### Python Dependencies:
```bash
# Install backend dependencies
cd backend
pip install -r requirements.txt
cd ..

# Or install minimal requirements
pip install -r requirements_minimal.txt
```

#### Node.js Dependencies:
```bash
# Install root dependencies
npm install

# Install frontend dependencies
cd frontend
npm install
cd ..
```

## 🔍 Verify Setup

Run the environment check:
```bash
python check_environment.py
```

This will verify:
- ✅ Environment files exist
- ✅ API key is configured
- ✅ Required directories exist
- ✅ Python dependencies are installed
- ✅ Node.js dependencies are installed

## 🚀 Start the Application

### Option 1: Full Application (Recommended)
```bash
# Start both backend and frontend
python run_nodejs.py
```

### Option 2: Windows Batch File
```bash
# Double-click or run
start_nodejs.bat
```

### Option 3: Manual Start
```bash
# Terminal 1: Start Python backend
cd backend
python run.py

# Terminal 2: Start Node.js frontend
npm start
```

## 🌐 Access Points

Once running, you can access:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **WebSocket**: ws://localhost:8080

## 🔧 Configuration Options

### OpenAI Models
You can change the model in your `.env` file:
- `gpt-4` (recommended, most accurate)
- `gpt-4-turbo` (faster, good accuracy)
- `gpt-3.5-turbo` (fastest, lower cost)

### Analysis Method
Currently set to `llm` (OpenAI only). This is the recommended setting for best results.

### File Size Limits
Default is 50MB. You can adjust `MAX_FILE_SIZE` in your `.env` file.

## 🐛 Troubleshooting

### Common Issues:

1. **"OPENAI_API_KEY not set"**
   - Make sure you've created the `.env` files
   - Verify the API key is correct (starts with `sk-`)
   - Check that the key is not the placeholder value

2. **"Module not found" errors**
   - Run: `pip install -r requirements.txt`
   - Or: `pip install -r requirements_minimal.txt`

3. **"Node modules not found"**
   - Run: `npm install`
   - Run: `cd frontend && npm install`

4. **Port already in use**
   - Kill processes on ports 3000, 8000, 8080
   - Or change ports in your `.env` files

5. **CORS errors**
   - Make sure `FRONTEND_URL` is set in backend `.env`
   - Verify the frontend URL is correct

### Getting Help:

1. Run `python check_environment.py` to diagnose issues
2. Check the logs in your terminal
3. Verify all environment variables are set correctly
4. Ensure all dependencies are installed

## 📝 Next Steps

After successful setup:
1. Upload a PDF document
2. Test the analysis functionality
3. Verify export features work
4. Deploy to production when ready

## 🔒 Security Notes

- Never commit your `.env` files to version control
- Keep your OpenAI API key secure
- Use environment variables in production
- Consider using a secrets management service for production deployments
