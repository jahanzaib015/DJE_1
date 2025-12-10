# Text Extraction Troubleshooting Guide

## Problem: Text Length is 0

If you see `text length: 0` in the logs or trace files, it means the PDF text extraction failed. Here's how to diagnose and fix it.

## Quick Diagnosis

### Step 1: Check Trace Files
1. Find your trace ID from the analysis logs
2. Navigate to `backend/traces/{trace_id}/`
3. Open `00_meta.json` and check:
   - `text_length`: Should be > 0
   - `char_count`: Should be > 0
   - `extraction_methods`: See which methods were tried

### Step 2: Check Clean Text
Open `20_clean_text.txt`:
- If empty → Text extraction completely failed
- If very short (< 100 chars) → Partial extraction or image-based PDF
- If contains text → Extraction worked, issue is elsewhere

## Common Causes and Solutions

### Cause 1: Image-Based PDF (Scanned Document)

**Symptoms:**
- `text_length: 0`
- `char_count: 0`
- `extraction_methods` shows all methods failed except OCR

**Solution:**
Install Tesseract OCR:

**Windows:**
```powershell
# Using Chocolatey
choco install tesseract

# Or download from: https://github.com/UB-Mannheim/tesseract/wiki
```

**Linux:**
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
```

**Mac:**
```bash
brew install tesseract
```

**Verify Installation:**
```bash
tesseract --version
```

### Cause 2: PDF with Special Encoding

**Symptoms:**
- Some extraction methods work, others fail
- Text is garbled or missing characters

**Solution:**
The system automatically tries multiple extraction methods:
1. PyMuPDF (best for most PDFs)
2. pdfminer (fallback)
3. PyPDF2 (last resort)
4. OCR (if text count is low)

Check `extraction_methods` in metadata to see which succeeded.

### Cause 3: Corrupted PDF File

**Symptoms:**
- All extraction methods fail
- Error messages in logs

**Solution:**
1. Try opening the PDF in a PDF viewer
2. If it doesn't open, the file is corrupted
3. Re-download or re-scan the document

### Cause 4: Empty or Blank Pages

**Symptoms:**
- `total_pages` > 0 but `char_count: 0`
- All pages extracted but no text

**Solution:**
This is expected for blank pages. Check if the PDF actually contains text by opening it manually.

## Enhanced Error Handling

The system now includes enhanced error handling:

1. **Automatic OCR Fallback**: If text extraction returns 0 characters, the system automatically tries OCR
2. **Detailed Logging**: Check logs for specific error messages
3. **Trace Files**: All extraction attempts are logged in trace files

## Checking Extraction Methods

In `00_meta.json`, check the `extraction_methods` array:

```json
{
  "extraction_methods": [
    {
      "method": "pymupdf",
      "char_count": 0,
      "success": false,
      "error": "No text found"
    },
    {
      "method": "ocr",
      "char_count": 12345,
      "success": true
    }
  ]
}
```

This tells you:
- Which methods were tried
- Which succeeded/failed
- How many characters each extracted

## Manual Testing

You can test text extraction manually:

```python
from backend.app.utils.file_handler import FileHandler

file_handler = FileHandler()
result = await file_handler.extract_pdf_text_with_tracing(
    "path/to/your/file.pdf",
    "test_trace_id"
)

print(f"Text length: {len(result['clean_text'])}")
print(f"Pages: {result['total_pages']}")
print(f"Methods: {result['extraction_methods']}")
```

## Next Steps

1. **If text extraction works but results are wrong:**
   - Check `20_clean_text.txt` - verify German checkbox patterns (X, -) are preserved
   - Check `40_llm_prompt.json` - verify text is in the prompt
   - Check `50_llm_response.json` - see what LLM returned

2. **If text extraction fails:**
   - Install OCR (Tesseract)
   - Check PDF is not corrupted
   - Verify PDF actually contains text (not just images)

3. **If text is extracted but LLM returns 0 rules:**
   - This is a different issue (LLM interpretation)
   - Check the German checkbox pattern recognition in prompts
   - Verify the text contains the table with checkboxes





