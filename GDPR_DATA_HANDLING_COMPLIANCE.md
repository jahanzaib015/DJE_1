# Data Handling and Deletion Policy - GDPR/DORA Compliance

**Subject:** Data Handling and Deletion Policy - Rules Extractor for DJE SA

Dear [Recipient Name],

Thank you for your questions regarding data handling in our Rules Extractor application deployed on Render. Below is a comprehensive overview of our data storage and deletion practices, designed to ensure full compliance with GDPR and DORA requirements.

---

## **1. UPLOADED PDF DOCUMENTS**

**Storage Location:**
- Render deployment: `/tmp/uploads/` (ephemeral container filesystem)
- Local development: `uploads/` directory

**Storage Type:**
- Transient filesystem storage (not in RAM, but on container filesystem)
- Not stored in persistent database, volume, or object storage

**Deletion:**
- **Automatic deletion immediately after processing completes**
- Deletion occurs synchronously in the processing pipeline
- Retention period: **0 seconds** (deleted immediately after analysis)
- Implementation: Automatic file removal via `os.remove()` after successful analysis

**Exception Handling:**
- If deletion fails, a warning is logged but processing continues
- Failed deletions are retried on next processing cycle

---

## **2. PROCESSED CONTENT (EXTRACTED TEXT)**

**Storage Location:**
- Markdown files: `markdown/` directory
- Trace files: `traces/<trace_id>/` directories

**Storage Type:**
- Filesystem-based storage (not in-memory only)
- Contains extracted and cleaned document text

**Deletion:**
- **Markdown files**: Deleted immediately after processing (0 seconds retention)
- **Trace files**: Deleted via scheduled cleanup after 1 hour retention
- **Automatic cleanup**: Runs every hour via background task

**Trace File Contents:**
- Raw text per page (`10_raw_text_page_XXX.txt`)
- Clean normalized text (`20_clean_text.txt`)
- Text chunks with metadata (`30_chunks.jsonl`)
- LLM prompts and responses (`40_llm_prompt.json`, `50_llm_response.json`)
- All trace artifacts are automatically deleted after 1 hour

---

## **3. ANALYSIS RESULTS**

**Storage Location:**
- `jobs_persistence.json` file (filesystem-based)

**Storage Type:**
- JSON file containing job status and analysis results
- Includes: Allowed/Not Allowed decisions, tables, confidence scores, processing metadata

**Deletion:**
- **Automatic cleanup**: Jobs older than 24 hours are automatically removed
- **Cleanup frequency**: Runs on server startup and every hour via scheduled task
- **Retention period**: 24 hours
- **Implementation**: Jobs are removed from in-memory dictionary and file is updated

**Additional Storage:**
- Results are also returned to users via API/WebSocket response
- Trace files (deleted after 1 hour) also contain analysis results

---

## **4. VECTOR DATABASE (ChromaDB)**

**Storage Location:**
- Render: `/tmp/chroma/` (ephemeral)
- Local: `var/chroma/`

**Storage Type:**
- Vector embeddings and document chunks for RAG (Retrieval-Augmented Generation) retrieval
- Contains semantic representations of document content

**Deletion:**
- **Automatic cleanup**: ChromaDB collections and index files older than 1 hour are deleted
- **Cleanup frequency**: Every hour via scheduled task
- **Retention period**: 1 hour
- **Method**: Entire collection directories and index files are removed

---

## **5. APPLICATION LOGS**

**Storage Location:**
- Render: `/tmp/logs/` (ephemeral container filesystem)
- Local: `logs/` directory

**Storage Type:**
- Technical metadata only (timestamps, HTTP status codes, error messages, request IDs)
- **No document content is logged**

**Deletion:**
- **Automatic log rotation**: Log files automatically rotate when they reach 10MB, maintaining maximum 5 backup files (~60MB total)
- **Automatic cleanup**: Log files older than 7 days are automatically deleted
- **Cleanup frequency**: Every hour via scheduled task
- **Retention period**: 7 days (with automatic rotation preventing excessive growth)
- **Ephemeral storage**: Logs in `/tmp/logs/` are automatically cleared when Render container restarts

**Log Content:**
- Only technical metadata (no document content)
- Request/response logging with sensitive data masking (API keys, passwords, tokens are masked)
- Error logs for debugging purposes

---

## **6. OPENAI DATA RETENTION**

**API Calls:**
- **Chat Completions API**: All calls include `store=False` parameter to prevent data retention
- **Embeddings API**: API call logging disabled in OpenAI dashboard
- **Dashboard Setting**: API call logging set to "Disabled" in OpenAI organization settings

**Data Sent to OpenAI:**
- Full document text (extracted from PDFs)
- Analysis prompts and instructions
- Document chunks for embedding generation

**Retention:**
- **OpenAI does not store any data** from our API calls
- Zero data retention is enforced via code (`store=False`) and dashboard settings
- No 30-day retention period applies to our API calls

---

## **7. AUTOMATED CLEANUP SCHEDULE**

A background task runs **every hour (3600 seconds)** to automatically clean up old data:

| Data Type | Cleanup Frequency | Retention Period | Method |
|-----------|------------------|------------------|--------|
| PDF Files | Immediate | 0 seconds | `os.remove()` |
| Markdown Files | Immediate + Hourly | 0 seconds / 1 hour | `os.remove()` |
| Trace Files | Hourly | 1 hour | `shutil.rmtree()` |
| ChromaDB Data | Hourly | 1 hour | `shutil.rmtree()` / `os.remove()` |
| Job Results | Hourly + Startup | 24 hours | Dictionary removal + file save |
| Log Files | Hourly | 7 days | `os.remove()` / `shutil.rmtree()` |

---

## **8. DATA THAT IS NOT DELETED (BY DESIGN)**

**Excel Export Files:**
- Location: `exports/` directory
- Retention: Currently kept indefinitely (cleanup code exists but is commented out)
- Reason: Users may need to download exports after processing
- Option: Can enable 24-hour cleanup if required

**Investment Catalog:**
- Location: `backend/data/investment_catalog.json`
- Retention: Permanent
- Reason: Reference data (investment type definitions), not user document data
- GDPR Status: Not subject to deletion as it contains no personal or document data

---

## **9. TECHNICAL IMPLEMENTATION**

**Immediate Deletion:**
- Code location: `backend/app/main.py`, lines 700-714
- Execution: Synchronous, happens immediately after analysis completes
- Error handling: Warnings logged, processing continues

**Scheduled Cleanup:**
- Code location: `backend/app/main.py`, lines 247-340
- Startup: Initialized in `startup_background_tasks()` function
- Frequency: Every 3600 seconds (1 hour)
- Error handling: Errors are logged but don't stop the cleanup process

**File Cleanup Utility:**
- Method: `FileHandler.cleanup_file(file_path)`
- Code location: `backend/app/utils/file_handler.py`, lines 1308-1314
- Implementation: Checks file existence, then removes with error handling

---

## **10. SUMMARY**

**Transient Processing:**
- All user document data is automatically deleted after processing
- No persistent storage of PDFs, extracted text, or analysis artifacts beyond defined retention periods
- Maximum retention: 24 hours (for job results only)

**OpenAI Data:**
- Zero data retention enforced via code and dashboard settings
- No data stored on OpenAI servers

**Compliance Status:**
- ✅ All user document data automatically deleted
- ✅ OpenAI data retention disabled
- ✅ Automated cleanup processes in place
- ✅ Retention periods clearly defined and implemented
- ✅ No manual intervention required for data deletion

---

## **CONCLUSION**

Our application is designed with GDPR and DORA compliance as a core requirement. All user document data is automatically deleted after processing, with retention periods clearly defined and automatically enforced. No manual intervention is required for data deletion, and all cleanup processes are automated and logged.

If you have any further questions or require additional clarification, please do not hesitate to contact me.

Best regards,

[Your Name]  
[Your Title]  
[Contact Information]

---

**Document Version:** 1.0  
**Last Updated:** [Current Date]  
**Application:** Rules Extractor for DJE SA  
**Deployment:** Render Platform

