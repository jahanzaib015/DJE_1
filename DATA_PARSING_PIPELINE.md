# Data Parsing Pipeline Documentation

This document explains how your data is parsed from PDF documents through the entire analysis pipeline.

## Overview

Your system processes PDF documents through multiple stages:
1. **PDF Text Extraction** - Extracts raw text from PDF files
2. **Text Cleaning & Normalization** - Cleans and normalizes the extracted text
3. **Table Extraction** - Extracts structured tables from PDFs
4. **Text Chunking** - Splits text into manageable chunks for analysis
5. **LLM Analysis** - Uses AI to extract investment rules from the text
6. **Result Processing** - Structures and validates the extracted rules

---

## 1. PDF Text Extraction

**Location**: `backend/app/utils/file_handler.py`

### Extraction Methods (Fallback Chain)

The system tries multiple extraction methods in order until one succeeds:

1. **PyMuPDF (Primary)** - Best for most PDFs
   - Extracts text from all pages
   - Preserves formatting and structure
   - Logs progress every 25 pages

2. **pdfminer (Fallback)** - Alternative extraction method
   - Uses form feed characters to split pages
   - Good for complex PDF structures

3. **PyPDF2 (Final Fallback)** - Basic extraction
   - Simple text extraction
   - Used when other methods fail

### OCR Support

If text extraction yields very little text (< 2000 characters), the system automatically attempts OCR:
- Converts PDF pages to images using `pdftoppm`
- Runs Tesseract OCR on each image
- Preserves special characters like "X" and "-" marks (critical for German investment documents)

### Image-Only PDF Detection

The system detects image-only (scanned) PDFs by:
- Checking if extracted text is empty or very short (< 500 chars total)
- Calculating average characters per page (< 100 chars/page = likely image-only)
- Automatically switching to vision-based analysis pipeline

---

## 2. Text Cleaning & Normalization

**Location**: `backend/app/utils/file_handler.py` → `_clean_text_robust()`

### Cleaning Steps

1. **Fix Hyphenation**: Rejoins words split across line breaks
   - Example: `"prohibi-\nted"` → `"prohibited"`

2. **Unicode Normalization**: Normalizes special characters
   - Converts ligatures (fi, ff) to standard characters
   - Uses NFKC normalization

3. **Fix OCR Errors**:
   - Fixes word spacing issues
   - Adds missing spaces before capital letters

4. **Whitespace Cleanup**:
   - Collapses multiple blank lines to double newlines
   - Removes excessive whitespace

5. **Remove Artifacts**:
   - Removes standalone page numbers
   - Removes "Page X of Y" headers/footers

---

## 3. Table Extraction

**Location**: `backend/app/utils/file_handler.py` → `_extract_tables()`

### Table Extraction Methods

Uses **Camelot** library with two flavors:

1. **Lattice Method** - For line-drawn tables (with visible borders)
2. **Stream Method** - For text-based tables (without borders)

### Table Processing

- Converts tables to markdown format for better LLM processing
- Extracts table metadata (page number, accuracy, method)
- Stitches tables back into text with clear markers
- Preserves table structure for analysis

### Critical for German Documents

German investment documents often use tables with "ja" (yes) and "nein" (no) columns:
- **"X" in "ja" column** = Instrument is ALLOWED
- **"X" in "nein" column** = Instrument is NOT ALLOWED
- **"-" in either column** = Typically NOT ALLOWED

---

## 4. Text Chunking

**Location**: `backend/app/utils/file_handler.py` → `chunk_text()`

### Chunking Strategy

Uses **LangChain's RecursiveCharacterTextSplitter** (if available):

- **Chunk Size**: ~1000 characters (~700-1000 tokens)
- **Overlap**: 150 characters (15% overlap for context preservation)
- **Separators**: `["\n\n", "\n", ". ", ";", " "]` (tries to split at natural boundaries)

### Chunk Metadata

Each chunk includes:
- `chunk_id`: Sequential identifier
- `start_char` / `end_char`: Character positions in original text
- `text`: The chunk content
- `length`: Character count
- `token_estimate`: Estimated token count (chars ÷ 4)
- `prev_chunk` / `next_chunk`: Links to adjacent chunks
- `has_negations`: Boolean flag if chunk contains negation cues
- `type`: Chunk type (usually "text")

### Fallback Chunking

If LangChain is unavailable, uses NLTK-based sentence-aware chunking:
- Splits text into sentences first
- Groups sentences into chunks
- Preserves context around negation cues (important for "not allowed" rules)

---

## 5. LLM Analysis

**Location**: `backend/app/services/llm_service.py` and `backend/app/services/providers/openai_provider.py`

### Analysis Process

1. **Text Preparation**:
   - For large documents (>200KB), uses section-based chunking
   - Sends text to LLM with detailed extraction prompts

2. **Extraction Rules** (from system prompts):

   **Default Assumption**: All instruments are **NOT ALLOWED** unless explicitly stated as allowed/permitted.

   **German Document Patterns** (Highest Priority):
   - Tables with "ja"/"nein" columns are the PRIMARY format
   - "X" in "ja" column = ALLOWED
   - "X" in "nein" column = NOT ALLOWED
   - Sections like "Zulässige Anlagen" (Permitted Investments) → extract ALL items as allowed=true
   - Sections like "Unzulässige Anlagen" (Prohibited Investments) → extract ALL items as allowed=false

   **Language Recognition**:
   - **Allowed**: "permitted", "allowed", "authorized", "erlaubt", "zugelassen", "darf"
   - **Prohibited**: "prohibited", "forbidden", "verboten", "nicht erlaubt", "darf nicht"

3. **Extraction Output**:
   - `instrument_rules`: List of instruments with allowed/prohibited status
   - `sector_rules`: Sector-based restrictions
   - `country_rules`: Geographic restrictions
   - `conflicts`: Contradictory rules or ambiguous statements

### Evidence Requirements

- Each rule must include **exact quotes** from the document (verbatim)
- Evidence must be ≤300 characters
- Includes enough context to make the rule clear

---

## 6. Result Processing

**Location**: `backend/app/services/analysis_service.py`

### Processing Steps

1. **Classification**: Maps extracted instruments to standardized categories using Excel mapping
2. **Validation**: Ensures extracted rules are evidence-based (no over-generalization)
3. **Structure**: Organizes results into OCRD JSON format
4. **Excel Export**: Creates formatted Excel files with results

### Excel Export Format

**Location**: `app/utils/file_handler.py` → `create_excel_export()`

Columns:
- **Section**: Rule category (instruments, sectors, countries)
- **Instrument**: Instrument name
- **Allowed**: Checkmark if allowed
- **Note**: Additional notes
- **Evidence**: Exact quote from document (for allowed items)

---

## Data Flow Summary

```
PDF File
  ↓
[Text Extraction] → PyMuPDF → pdfminer → PyPDF2 → OCR (if needed)
  ↓
[Text Cleaning] → Fix hyphenation, normalize unicode, remove artifacts
  ↓
[Table Extraction] → Camelot (lattice/stream) → Convert to markdown
  ↓
[Text Chunking] → LangChain RecursiveCharacterTextSplitter
  ↓
[RAG Indexing] → ChromaDB vector store (for retrieval)
  ↓
[LLM Analysis] → OpenAI/Anthropic → Extract investment rules
  ↓
[Result Processing] → Classification → Validation → OCRD JSON
  ↓
[Excel Export] → Formatted spreadsheet with results
```

---

## Key Features

### Robust Fallback Chain
- Multiple extraction methods ensure text is extracted even from difficult PDFs
- Automatic OCR fallback for image-based PDFs

### German Document Support
- Special handling for German investment documents
- Recognizes "ja"/"nein" table patterns
- Understands German section headers ("Zulässige Anlagen", etc.)

### Evidence-Based Extraction
- Every rule includes exact quotes from the document
- No inference or guessing - only explicit rules are extracted
- Completeness verification ensures all rules are found

### Large Document Handling
- Processes documents of any size (100+ pages)
- Section-by-section processing for very long documents
- Progress logging for monitoring

---

## Trace Files (Debugging)

When tracing is enabled, the system saves intermediate files:
- `10_raw_text_page_N.txt`: Raw extracted text per page
- `20_clean_text.txt`: Cleaned and normalized text
- `30_chunks.jsonl`: Text chunks in JSONL format
- `40_tables.json`: Extracted tables
- `50_rag_index.json`: RAG indexing results
- `00_meta.json`: Metadata about the extraction process

These files help debug parsing issues and verify extraction quality.



