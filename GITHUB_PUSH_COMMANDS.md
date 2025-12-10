# GitHub Push Commands - Step by Step

## 🚀 Complete Guide to Push Your Code to GitHub

### Step 1: Check if Git is Initialized

```bash
cd c:\Users\JahanzaibHussain\Downloads\ocrd_extractor_upgrade_latest
git status
```

**If you see "not a git repository":**
```bash
git init
```

### Step 2: Verify .env Files are NOT Tracked (CRITICAL!)

```bash
# Check if .env files are tracked (should return nothing)
git ls-files | findstr ".env"

# If any .env files show up, remove them from tracking:
git rm --cached .env 2>nul
git rm --cached backend/.env 2>nul
git rm --cached frontend/.env 2>nul
```

### Step 3: Check Current Status

```bash
git status
```

### Step 4: Add All Files (except .env files which are in .gitignore)

```bash
git add .
```

### Step 5: Verify What Will Be Committed

```bash
# Check that .env files are NOT in the staging area
git status
```

### Step 6: Create Initial Commit (or add to existing)

```bash
# If this is your first commit:
git commit -m "Initial commit: OCRD Extractor with fallback prompt mechanism"

# Or if you have existing commits:
git commit -m "Add fallback prompt for investment guideline documents"
```

### Step 7: Add GitHub Remote (if not already added)

**Option A: Create new repository on GitHub first, then:**
```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
```

**Option B: If remote already exists, check it:**
```bash
git remote -v
```

### Step 8: Push to GitHub

```bash
# For first push:
git branch -M main
git push -u origin main

# For subsequent pushes:
git push origin main
```

---

## 📋 Complete Command Sequence (Copy & Paste)

```bash
# Navigate to project directory
cd c:\Users\JahanzaibHussain\Downloads\ocrd_extractor_upgrade_latest

# Initialize git if needed
git init

# Verify .env files are ignored
git check-ignore .env backend/.env frontend/.env

# Check status
git status

# Remove .env files from tracking if they're tracked
git rm --cached .env 2>nul
git rm --cached backend/.env 2>nul
git rm --cached frontend/.env 2>nul

# Add all files
git add .

# Verify .env files are NOT in staging
git status

# Commit
git commit -m "Initial commit: OCRD Extractor with enhanced fallback prompt"

# Add remote (replace with your GitHub repo URL)
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git

# Push to GitHub
git branch -M main
git push -u origin main
```

---

## 🔍 Troubleshooting

### If you get "fatal: remote origin already exists":
```bash
# Check current remote
git remote -v

# Update remote URL if needed
git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
```

### If you get authentication errors:
```bash
# Use GitHub CLI or Personal Access Token
# Or use SSH instead:
git remote set-url origin git@github.com:YOUR_USERNAME/YOUR_REPO_NAME.git
```

### If .env files are still showing:
```bash
# Force remove from cache
git rm --cached -r .env backend/.env frontend/.env
git commit -m "Remove .env files from tracking"
```

---

## ✅ Final Verification

After pushing, verify on GitHub:
1. Go to your repository on GitHub
2. Check that `.env` files are NOT visible
3. Check that no API keys are in any files
4. Verify all your code files are there
