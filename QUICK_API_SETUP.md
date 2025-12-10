# ⚡ Quick API Setup (30 seconds)

## 🎯 Two Files to Configure

### 1️⃣ Backend API Key (OpenAI)

**File Location**: `backend/.env`

**What to add:**
```env
OPENAI_API_KEY=sk-your-actual-openai-api-key-here
```

**Steps:**
1. Go to `backend` folder
2. Create file named `.env` (if it doesn't exist)
3. Add the line above with your actual OpenAI API key
4. Save

**Get your key**: https://platform.openai.com/api-keys

---

### 2️⃣ Frontend API URL (Where Frontend Connects)

**File Location**: `frontend/.env`

**What to add:**
```env
REACT_APP_API_URL=http://localhost:8000
REACT_APP_WS_URL=ws://localhost:8000
PORT=3000
```

**Steps:**
1. Go to `frontend` folder
2. Create file named `.env` (if it doesn't exist)
3. Add the lines above
4. Save
5. **IMPORTANT**: Restart frontend after changing this file!

---

## 📁 File Structure

```
ocrd_extractor_upgrade_latest/
├── backend/
│   └── .env          ← Add OpenAI API key here
├── frontend/
│   └── .env          ← Add API URL here
└── ...
```

---

## ✅ Test It

1. **Start Backend**: `cd backend && py run.py`
2. **Start Frontend**: `cd frontend && npm start`
3. **Open Browser**: http://localhost:3000
4. **Click**: "Test Connection" button

If it works, you're all set! 🎉






