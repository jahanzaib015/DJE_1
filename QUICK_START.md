# 🚀 Quick Start Guide

## Step 1: Set Up Environment Variables

1. **Edit `backend/.env` file** and add your OpenAI API key:
   ```
   OPENAI_API_KEY=sk-your-actual-api-key-here
   ```

2. **Get your OpenAI API key** from: https://platform.openai.com/api-keys

## Step 2: Run the Application

### Option A: Easy Start (Recommended)
Double-click or run:
```bash
start_local.bat
```

This will:
- ✅ Create virtual environment (if needed)
- ✅ Install all dependencies
- ✅ Start backend server (port 8000)
- ✅ Start frontend (port 3000)

### Option B: Manual Start

**Backend only:**
```bash
cd backend
py run.py
```

**Frontend only:**
```bash
cd frontend
npm start
```

## Step 3: Access the Application

- **Frontend UI**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## Troubleshooting

### If backend fails to start:
1. Check `backend/.env` has `OPENAI_API_KEY` set
2. Make sure port 8000 is not in use
3. Check Python version: `py --version` (needs 3.8+)

### If frontend fails to start:
1. Make sure Node.js is installed: `node --version`
2. Install dependencies: `cd frontend && npm install`
3. Check port 3000 is not in use

### Common Issues:
- **Port already in use**: Change PORT in `.env` or kill the process using the port
- **Missing dependencies**: Run `pip install -r backend/requirements.txt`
- **API key not working**: Verify your OpenAI API key is valid and has credits
