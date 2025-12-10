# 🔧 Fix Connection 404 Error

## Issue
The frontend is showing "Connection test failed: Request failed with status code 404"

## Solution

### Step 1: Check Backend is Running

1. Look for a command window titled **"OCRD Backend"**
2. It should show: `Uvicorn running on http://0.0.0.0:8000`
3. If you don't see this window, the backend is not running

### Step 2: Fix Frontend Environment File

Edit `frontend/.env` file and make sure it has:

```env
REACT_APP_API_URL=http://localhost:8000
REACT_APP_WS_URL=ws://localhost:8000
PORT=3000
```

**Important**: Make sure `REACT_APP_API_URL` points to port **8000** (backend), NOT port 3000!

### Step 3: Restart Frontend

After updating the `.env` file:
1. Close the frontend window (press Ctrl+C)
2. Restart it:
   ```bash
   cd frontend
   npm start
   ```

### Step 4: Verify Backend is Running

Open a new terminal and check:
```bash
curl http://localhost:8000/api/health
```

Or visit in browser: http://localhost:8000/api/health

You should see: `{"status":"healthy","timestamp":"..."}`

### Step 5: Manual Backend Start (If Needed)

If backend is not running, start it manually:

```bash
venv\Scripts\activate
cd backend
py run.py
```

You should see:
```
🚀 Starting OCRD Extractor API...
🌐 Server will be available at: http://localhost:8000
```

### Quick Fix Script

Run this to check everything:

```bash
# Check if backend is running
netstat -ano | findstr :8000

# If nothing shows, start backend:
venv\Scripts\activate
cd backend
py run.py
```

Then restart the frontend after fixing the `.env` file.






