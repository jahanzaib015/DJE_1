# Render Port Binding Fix

## Problem
Render is running: `uvicorn app.main:app --host 0.0.0.0 --port 10000`
But getting: "No open ports detected"

## Root Cause
Render is running the command from the **root directory**, not the `backend/` directory, so it can't find `app.main:app`.

## Solution Applied

### 1. Updated `render.yaml` startCommand:
```yaml
startCommand: |
  cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

### 2. Updated `backend/Procfile`:
```
web: cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Why This Works
- `cd backend` ensures we're in the correct directory
- `app.main:app` can then be found (it's in `backend/app/main.py`)
- `${PORT:-8000}` uses Render's $PORT env var, with 8000 as fallback
- The app will bind to the port Render assigns

## Next Steps

1. **Push the changes:**
   ```bash
   git add render.yaml backend/Procfile
   git commit -m "Fix Render port binding - run from backend directory"
   git push origin main
   ```

2. **Verify in Render Dashboard:**
   - Go to your service settings
   - Check "Start Command" shows: `cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - If it doesn't match, Render might be using Procfile instead

3. **If Render uses Procfile:**
   - Make sure `backend/Procfile` exists with the correct command
   - Or delete root `Procfile` if it's interfering

4. **Redeploy:**
   - Render should auto-deploy after push
   - Or manually trigger deployment

## Alternative: Use Absolute Path

If the above doesn't work, try this in render.yaml:

```yaml
startCommand: |
  cd backend && PYTHONPATH=/opt/render/project/src/backend:$PYTHONPATH python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Verify Port Binding

After deployment, check logs for:
```
INFO:     Uvicorn running on http://0.0.0.0:XXXX (Press CTRL+C to quit)
```

If you see this, the port is bound correctly!
