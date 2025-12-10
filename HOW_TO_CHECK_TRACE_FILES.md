# How to Check Trace Files

## Overview

Trace files are automatically created for every analysis and stored in the `traces/` directory. They contain all intermediate artifacts from the analysis pipeline, allowing you to debug issues and verify text extraction.

## Finding Your Trace ID

1. **From the UI**: After running an analysis, look for the trace ID in:
   - The browser console (F12 → Console tab)
   - The analysis results page
   - The job status response

2. **From the Backend Logs**: Look for lines like:
   ```
   🔍 Starting LLM analysis (TRACED) with openai/gpt-5, text length: 12345
   ```
   The trace ID is usually logged near the start of the analysis.

3. **From the File System**: Navigate to the `traces/` directory:
   ```bash
   cd backend/traces
   ls -la
   ```
   Each folder is a trace ID (e.g., `trace_1234567890_abc12345`)

## Accessing Trace Files via API

### 1. Get Trace Metadata
```bash
curl http://localhost:8000/api/traces/{trace_id}
```

This returns:
- `trace_id`: Unique identifier
- `text_length`: Length of extracted text (check this first!)
- `total_pages`: Number of pages in PDF
- `extraction_methods`: Methods used for text extraction
- `char_count`: Total characters extracted

### 2. Check Text Extraction Files

**Get Clean Text (most important):**
```bash
curl http://localhost:8000/api/traces/{trace_id}/files/20_clean_text.txt
```

**Get Raw Text from Page 1:**
```bash
curl http://localhost:8000/api/traces/{trace_id}/files/10_raw_text_page_001.txt
```

**Get All Pages:**
```bash
# Page 1
curl http://localhost:8000/api/traces/{trace_id}/files/10_raw_text_page_001.txt

# Page 2
curl http://localhost:8000/api/traces/{trace_id}/files/10_raw_text_page_002.txt

# etc.
```

### 3. Check LLM Input/Output

**Get LLM Prompt:**
```bash
curl http://localhost:8000/api/traces/{trace_id}/files/40_llm_prompt.json
```

**Get LLM Response:**
```bash
curl http://localhost:8000/api/traces/{trace_id}/files/50_llm_response.json
```

## Accessing Trace Files via File System

### Windows
```powershell
# Navigate to traces directory
cd backend\traces

# List all traces
dir

# Navigate to specific trace
cd trace_1234567890_abc12345

# View clean text
type 20_clean_text.txt

# View metadata
type 00_meta.json
```

### Linux/Mac
```bash
# Navigate to traces directory
cd backend/traces

# List all traces
ls -la

# Navigate to specific trace
cd trace_1234567890_abc12345

# View clean text
cat 20_clean_text.txt

# View metadata
cat 00_meta.json
```

## Key Files to Check

### 1. `00_meta.json` - **START HERE**
Contains:
- `text_length`: **Check this first!** If 0, text extraction failed
- `total_pages`: Number of pages extracted
- `char_count`: Total characters before cleaning
- `extraction_methods`: Which methods were tried
- `ocr_used`: Whether OCR was used

### 2. `20_clean_text.txt` - **MOST IMPORTANT**
This is the text that gets sent to the LLM. If this is empty or very short:
- Text extraction failed
- PDF might be image-based (needs OCR)
- PDF might have special encoding

### 3. `10_raw_text_page_XXX.txt` - Raw Extraction
Check individual pages to see if extraction worked per page.

### 4. `40_llm_prompt.json` - What Was Sent to LLM
Verify the text was actually included in the prompt.

### 5. `50_llm_response.json` - LLM Response
Check if LLM returned any instrument rules.

## Common Issues and Solutions

### Issue: `text_length: 0` in metadata

**Possible Causes:**
1. PDF is image-based (scanned document)
2. PDF has special encoding
3. Text extraction libraries failed

**Solutions:**
1. Check `00_meta.json` for `extraction_methods` - see which methods were tried
2. Check if `ocr_used: true` - if false, OCR might not be installed
3. View `20_clean_text.txt` - if empty, extraction definitely failed
4. Try installing OCR dependencies:
   ```bash
   # Windows (using Chocolatey)
   choco install tesseract
   
   # Linux
   sudo apt-get install tesseract-ocr
   
   # Mac
   brew install tesseract
   ```

### Issue: Text is extracted but LLM returns 0 rules

**Check:**
1. `20_clean_text.txt` - does it contain the table with checkboxes?
2. `40_llm_prompt.json` - is the text included in the prompt?
3. `50_llm_response.json` - what did the LLM return?

### Issue: German checkbox patterns not recognized

**Check:**
1. `20_clean_text.txt` - verify "X" and "-" characters are preserved
2. `40_llm_prompt.json` - verify German pattern instructions are in the prompt
3. `50_llm_response.json` - check if LLM understood the patterns

## Quick Diagnostic Script

Create a file `check_trace.py`:

```python
import json
import sys
import os

trace_id = sys.argv[1] if len(sys.argv) > 1 else None

if not trace_id:
    print("Usage: python check_trace.py <trace_id>")
    sys.exit(1)

trace_dir = f"backend/traces/{trace_id}"

# Check metadata
meta_path = f"{trace_dir}/00_meta.json"
if os.path.exists(meta_path):
    with open(meta_path, 'r') as f:
        meta = json.load(f)
    print(f"Text Length: {meta.get('text_length', 'N/A')}")
    print(f"Total Pages: {meta.get('total_pages', 'N/A')}")
    print(f"Char Count: {meta.get('char_count', 'N/A')}")
    print(f"Extraction Methods: {meta.get('extraction_methods', [])}")
else:
    print(f"Metadata file not found: {meta_path}")

# Check clean text
clean_text_path = f"{trace_dir}/20_clean_text.txt"
if os.path.exists(clean_text_path):
    with open(clean_text_path, 'r', encoding='utf-8') as f:
        clean_text = f.read()
    print(f"\nClean Text Length: {len(clean_text)}")
    print(f"First 500 chars:\n{clean_text[:500]}")
else:
    print(f"Clean text file not found: {clean_text_path}")
```

Run it:
```bash
python check_trace.py trace_1234567890_abc12345
```

## Browser Access (if frontend supports it)

If your frontend has a trace viewer, you can access it directly:
- Look for a "View Trace" or "Debug" button in the UI
- Or navigate to: `http://localhost:3000/traces/{trace_id}` (if implemented)





