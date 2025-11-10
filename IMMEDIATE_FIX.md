# ⚡ Immediate Fix for 404 Error

## The Problem
Your frontend is running but getting a 404 error because **the backend is not running**.

## Quick Fix (2 Steps)

### Step 1: Start the Backend

**Option A - Use the script:**
```bash
start_backend_only.bat
```

**Option B - Manual:**
```bash
venv\Scripts\activate
cd backend
py run.py
```

Wait until you see:
```
🚀 Starting OCRD Extractor API...
🌐 Server will be available at: http://localhost:8000
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 2: Fix Frontend Environment File

1. Open `frontend/.env` in a text editor
2. Make sure it contains:
   ```env
   REACT_APP_API_URL=http://localhost:8000
   REACT_APP_WS_URL=ws://localhost:8000
   PORT=3000
   ```
3. **IMPORTANT**: The URL must be `http://localhost:8000` (port 8000, not 3000!)

4. **Restart the frontend**:
   - Close the frontend window (Ctrl+C)
   - Run: `cd frontend && npm start`

## Verify It's Working

1. Backend should show: `Uvicorn running on http://0.0.0.0:8000`
2. Frontend should show: `Compiled successfully`
3. Open browser: http://localhost:3000
4. Click "Test Connection" - should now work!

## If Still Not Working

Check backend is accessible:
- Open browser: http://localhost:8000/api/health
- Should see: `{"status":"healthy","timestamp":"..."}`

If you see "This site can't be reached", the backend is not running.


