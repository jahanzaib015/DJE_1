# 🚀 Local Deployment Guide

This guide will help you deploy and run the OCRD Extractor application locally on your machine.

## 📋 Prerequisites

Before starting, ensure you have the following installed:

- **Python 3.8+** - [Download Python](https://www.python.org/downloads/)
- **Node.js 16+** - [Download Node.js](https://nodejs.org/)
- **npm** (comes with Node.js)
- **Git** (optional, if cloning from repository)

## 🎯 Quick Start (Recommended)

### Windows Users

1. **Double-click** `start_local.bat` or run it from command prompt:
   ```bash
   start_local.bat
   ```

The script will automatically:
- Create a Python virtual environment (if needed)
- Install all Python dependencies
- Install all Node.js dependencies
- Start both backend and frontend servers

### macOS/Linux Users

1. **Make the script executable**:
   ```bash
   chmod +x start_local.sh
   ```

2. **Run the script**:
   ```bash
   ./start_local.sh
   ```

## 🔧 Manual Setup

If you prefer to set up manually or the automated script doesn't work:

### Step 1: Set Up Python Backend

1. **Create and activate virtual environment**:
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install Python dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r backend/requirements.txt
   ```

3. **Set up environment variables**:
   ```bash
   # Copy the example file
   cp backend/env.example backend/.env

   # Edit backend/.env and add your OpenAI API key (optional)
   # For local development, you can leave it as is
   ```

4. **Start the backend**:
   ```bash
   cd backend
   python run.py
   ```

   The backend will be available at: **http://localhost:8000**

### Step 2: Set Up React Frontend

1. **Install Node.js dependencies**:
   ```bash
   # Install root dependencies
   npm install

   # Install frontend dependencies
   cd frontend
   npm install
   cd ..
   ```

2. **Set up environment variables**:
   ```bash
   # The frontend/.env file should already be created
   # It points to http://localhost:8000 for local development
   ```

3. **Start the frontend**:
   ```bash
   npm start
   ```

   The frontend will be available at: **http://localhost:3000**

## 🌐 Access Points

Once both services are running, you can access:

- **Frontend Application**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## ⚙️ Configuration

### Backend Configuration (`backend/.env`)

```env
# OpenAI API Configuration (optional)
OPENAI_API_KEY=your_openai_api_key_here

# Server Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=True

# File Upload Configuration
MAX_FILE_SIZE=50MB
UPLOAD_DIR=uploads
EXPORT_DIR=exports

# LLM Configuration
DEFAULT_LLM_PROVIDER=openai
DEFAULT_MODEL=gpt-4
DEFAULT_ANALYSIS_METHOD=llm_with_fallback
```

### Frontend Configuration (`frontend/.env`)

```env
# React App Configuration
REACT_APP_API_URL=http://localhost:8000
REACT_APP_WS_URL=ws://localhost:8000

# Development Configuration
PORT=3000
```

## 🐛 Troubleshooting

### Port Already in Use

If you get an error that port 8000 or 3000 is already in use:

**Windows:**
```bash
# Find process using port 8000
netstat -ano | findstr :8000

# Kill the process (replace PID with actual process ID)
taskkill /PID <PID> /F
```

**macOS/Linux:**
```bash
# Find process using port 8000
lsof -i :8000

# Kill the process (replace PID with actual process ID)
kill -9 <PID>
```

### Python Dependencies Installation Issues

If you encounter compilation errors:

```bash
# Try installing with binary packages only
pip install --only-binary=all -r backend/requirements.txt

# Or use minimal requirements
pip install -r requirements_minimal.txt
```

### Node.js Dependencies Issues

```bash
# Clear npm cache and reinstall
npm cache clean --force
rm -rf node_modules frontend/node_modules
npm install
cd frontend && npm install && cd ..
```

### Module Not Found Errors

Make sure your virtual environment is activated:

```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### Frontend Not Connecting to Backend

1. Verify backend is running on port 8000
2. Check `frontend/.env` has `REACT_APP_API_URL=http://localhost:8000`
3. Restart the frontend after changing `.env` files

## 📝 Next Steps

1. **Test the application**:
   - Open http://localhost:3000
   - Upload a PDF document
   - Run an analysis

2. **Configure OpenAI API** (optional):
   - Get your API key from [OpenAI Platform](https://platform.openai.com/api-keys)
   - Add it to `backend/.env`

3. **Explore the API**:
   - Visit http://localhost:8000/docs for interactive API documentation

## 🛑 Stopping the Services

- **Windows**: Press `Ctrl+C` in each terminal window, or close the terminal windows
- **macOS/Linux**: Press `Ctrl+C` in the terminal running the script

## 📚 Additional Resources

- [Main README](README.md) - General project information
- [Environment Setup](ENVIRONMENT_SETUP.md) - Detailed environment configuration
- [API Documentation](http://localhost:8000/docs) - Interactive API docs (when running)

## 💡 Tips

- **Development Mode**: The backend runs with auto-reload enabled, so changes are reflected immediately
- **Hot Reload**: The React frontend supports hot module replacement
- **Logs**: Check terminal output for both services to see requests and errors
- **First Run**: The first startup may take longer as dependencies are installed






