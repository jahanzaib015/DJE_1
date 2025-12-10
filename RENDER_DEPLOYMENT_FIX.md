# Render Deployment Fix for DJE 1-3

## Common Render Deployment Failures & Fixes

### Issue 1: Build Command Fails (apt-get not available)
**Problem:** Render's build environment may not support `apt-get` commands directly.

**Fix:** Update `render.yaml` build command:

```yaml
buildCommand: |
  pip install --upgrade pip
  cd backend
  pip install -r requirements.txt
  mkdir -p /tmp/chroma
```

**Note:** Tesseract and Poppler might not be available on Render free tier. Consider:
- Using a different PDF processing library
- Or upgrading to paid tier that supports system packages

### Issue 2: Missing Dependencies
**Problem:** Some packages in `requirements.txt` might not install on Render.

**Fix:** Create `backend/requirements_render.txt` with minimal dependencies:

```txt
fastapi==0.118.2
uvicorn[standard]==0.24.0
python-multipart==0.0.20
aiofiles==25.1.0
httpx==0.28.1
openai>=1.0.0
pydantic==2.12.0
python-dotenv==1.1.1
openpyxl==3.1.5
websockets==12.0
pypdf==6.1.1
PyPDF2==3.0.1
pandas==2.3.3
numpy>=1.24.0,<2.0.0
```

### Issue 3: Start Command Issues
**Problem:** The start command might not work correctly.

**Current (might fail):**
```yaml
startCommand: cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**Fixed Options:**

**Option A (Recommended):**
```yaml
startCommand: cd backend && python run.py
```

**Option B:**
```yaml
startCommand: cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
```

### Issue 4: Missing Environment Variables
**Required Environment Variables in Render Dashboard:**

1. Go to your service → Environment tab
2. Add these variables:

```
OPENAI_API_KEY=your_actual_key_here (mark as Secret)
HOST=0.0.0.0
PORT=8000
DEBUG=False
MAX_FILE_SIZE=50MB
UPLOAD_DIR=uploads
EXPORT_DIR=exports
DEFAULT_LLM_PROVIDER=openai
DEFAULT_MODEL=gpt-4o
DEFAULT_ANALYSIS_METHOD=llm
```

### Issue 5: Import Errors
**Problem:** Python path issues or missing modules.

**Fix:** Ensure `backend/app/__init__.py` exists and all imports are correct.

---

## Fixed render.yaml Configuration

Update your `render.yaml` in the root directory:

```yaml
services:
  - type: web
    name: ocrd-extractor-python-backend
    env: python
    plan: free
    buildCommand: |
      pip install --upgrade pip
      cd backend
      pip install -r requirements.txt
      mkdir -p /tmp/chroma
    startCommand: |
      cd backend && python run.py
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
      - key: PORT
        value: 8000
      - key: HOST
        value: 0.0.0.0
      - key: DEBUG
        value: "False"
      - key: OPENAI_API_KEY
        sync: false
        type: secret
```

---

## Step-by-Step Fix Process

### Step 1: Check Render Logs
1. Go to Render Dashboard
2. Click on your service "ocrd-extractor-python-backend"
3. Go to "Logs" tab
4. Check the **build logs** and **runtime logs**
5. Look for error messages

### Step 2: Common Error Messages & Fixes

**Error: "apt-get: command not found"**
- **Fix:** Remove `apt-get` commands from buildCommand
- Use only `pip install` commands

**Error: "ModuleNotFoundError: No module named 'X'"**
- **Fix:** Add missing package to `requirements.txt`
- Redeploy

**Error: "Port already in use" or "Address already in use"**
- **Fix:** Ensure `PORT` environment variable is set to `8000`
- Use `$PORT` in start command (Render sets this automatically)

**Error: "Failed to start" or "Application failed to respond"**
- **Fix:** Check start command is correct
- Verify `run.py` exists and works
- Check that app binds to `0.0.0.0:$PORT`

**Error: "OPENAI_API_KEY not found"**
- **Fix:** Add `OPENAI_API_KEY` as environment variable in Render dashboard
- Mark it as **Secret**

### Step 3: Test Locally First
Before deploying, test the start command locally:

```bash
cd backend
python run.py
```

If it works locally, it should work on Render.

### Step 4: Update render.yaml
Use the fixed configuration above.

### Step 5: Redeploy
1. Push updated `render.yaml` to GitHub
2. Render will auto-deploy
3. Or manually trigger deployment in Render dashboard

---

## Quick Fix Commands

If you need to update render.yaml quickly:

```bash
# Backup current render.yaml
cp render.yaml render.yaml.backup

# The fixed version is in RENDER_DEPLOYMENT_FIX.md above
# Copy the fixed configuration to render.yaml
```

---

## Alternative: Use Procfile Instead

If render.yaml doesn't work, you can use Procfile:

**backend/Procfile:**
```
web: cd backend && python run.py
```

Then in Render dashboard:
- **Build Command:** `pip install -r backend/requirements.txt`
- **Start Command:** (leave empty, uses Procfile)

---

## Still Having Issues?

1. **Check Render Logs** - Most errors are visible there
2. **Verify Environment Variables** - All required vars must be set
3. **Test Start Command Locally** - If it fails locally, it will fail on Render
4. **Check Python Version** - Must match `runtime.txt` (3.11.0)
5. **Verify Dependencies** - All packages in requirements.txt must be installable

---

## Minimal Working Configuration

For a minimal deployment that should work:

**render.yaml:**
```yaml
services:
  - type: web
    name: ocrd-extractor-python-backend
    env: python
    plan: free
    buildCommand: pip install -r backend/requirements.txt
    startCommand: cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
      - key: OPENAI_API_KEY
        sync: false
        type: secret
```

**Required Environment Variables in Render Dashboard:**
- `OPENAI_API_KEY` (Secret)
- `PORT=8000` (usually auto-set by Render)
- `HOST=0.0.0.0`
