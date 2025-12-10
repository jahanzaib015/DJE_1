# 🔑 API Key Configuration Guide

This guide shows you exactly where to configure API keys and URLs for both backend and frontend.

## 📍 Location 1: Backend API Key (OpenAI)

### File: `backend/.env`

**Create or edit this file** in the `backend` folder:

```env
# OpenAI API Configuration
OPENAI_API_KEY=sk-your-actual-api-key-here

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

**Important**: 
- Replace `sk-your-actual-api-key-here` with your actual OpenAI API key
- Get your key from: https://platform.openai.com/api-keys
- The key should start with `sk-`

### How to Edit:

1. **Navigate to**: `backend` folder
2. **Open or create**: `.env` file (if it doesn't exist, create it)
3. **Add your API key** on the `OPENAI_API_KEY=` line
4. **Save the file**

### Alternative: Use Setup Script

You can also run:
```bash
cd backend
python setup_api_key.py
```

This will prompt you to enter your API key interactively.

---

## 📍 Location 2: Frontend API URL (Client-Side)

### File: `frontend/.env`

**Create or edit this file** in the `frontend` folder:

```env
# React App Configuration
# Point to your backend API (port 8000 for local development)
REACT_APP_API_URL=http://localhost:8000
REACT_APP_WS_URL=ws://localhost:8000

# Development Configuration
PORT=3000
```

**Important**:
- `REACT_APP_API_URL` should point to your **backend** (port 8000), NOT the frontend (port 3000)
- For local development: `http://localhost:8000`
- For production: Replace with your production backend URL

### How to Edit:

1. **Navigate to**: `frontend` folder
2. **Open or create**: `.env` file
3. **Set** `REACT_APP_API_URL=http://localhost:8000`
4. **Save the file**

### After Changing Frontend .env:

**You MUST restart the frontend** for changes to take effect:
1. Stop the frontend (Ctrl+C)
2. Restart: `cd frontend && npm start`

---

## 📍 Location 3: Node.js Server (Optional)

If you're using the Node.js proxy server (`server.js`), configure:

### File: `.env` (root folder)

```env
# Node.js Server Configuration
PORT=3000
NODE_ENV=development
PYTHON_BACKEND_URL=http://localhost:8000
```

**Note**: This is only needed if you're running the Node.js proxy server.

---

## ✅ Quick Setup Checklist

- [ ] **Backend**: Create `backend/.env` with your OpenAI API key
- [ ] **Frontend**: Create `frontend/.env` with `REACT_APP_API_URL=http://localhost:8000`
- [ ] **Restart** both backend and frontend after making changes

---

## 🔍 Verify Configuration

### Check Backend API Key:

```bash
cd backend
python -c "from dotenv import load_dotenv; import os; load_dotenv(); key = os.getenv('OPENAI_API_KEY'); print('✅ API Key set' if key and key != 'your_openai_api_key_here' else '❌ API Key not set')"
```

### Check Frontend API URL:

The frontend will use `http://localhost:8000` by default if `REACT_APP_API_URL` is not set.

---

## 📝 Example Files

### `backend/.env` (Example)
```env
OPENAI_API_KEY=sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx234yz
HOST=0.0.0.0
PORT=8000
DEBUG=True
```

### `frontend/.env` (Example)
```env
REACT_APP_API_URL=http://localhost:8000
REACT_APP_WS_URL=ws://localhost:8000
PORT=3000
```

---

## 🚨 Common Mistakes

1. **Wrong port in frontend**: 
   - ❌ `REACT_APP_API_URL=http://localhost:3000` (frontend port)
   - ✅ `REACT_APP_API_URL=http://localhost:8000` (backend port)

2. **API key not in backend/.env**: 
   - Make sure the file is in the `backend` folder, not root

3. **Forgot to restart**: 
   - Frontend needs restart after changing `.env` file

4. **Using placeholder key**: 
   - Make sure to replace `your_openai_api_key_here` with your actual key

---

## 🆘 Need Help?

- Backend API key issues: Check `backend/config.py` loads from `.env`
- Frontend connection issues: Check `frontend/src/services/AnalysisService.ts` uses `REACT_APP_API_URL`
- Test connection: Use the "Test Connection" button in the frontend






