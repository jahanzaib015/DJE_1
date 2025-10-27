# Forensic Pipeline Documentation

## Overview

The forensic pipeline provides complete traceability for document analysis requests. Each analysis creates a unique trace folder containing all intermediate artifacts, allowing you to debug issues and understand exactly what happened during processing.

## Trace Structure

Each trace is stored in `/traces/<trace_id>/` with the following files:

### 00_meta.json
Contains metadata about the analysis:
- `trace_id`: Unique identifier
- `job_id`: Job identifier
- `filename`: Original PDF filename
- `file_path`: Full path to uploaded file
- `analysis_method`: Analysis method used
- `llm_provider`: LLM provider (openai, ollama)
- `model`: Specific model used
- `fund_id`: Fund identifier
- `ocr_enabled`: Whether OCR was used
- `extractor`: Text extraction method (PyPDF2)
- `total_pages`: Number of pages in PDF
- `extraction_time`: Time taken for text extraction
- `text_length`: Length of extracted text
- `chunks_count`: Number of text chunks created
- `start_time`: Analysis start timestamp
- `created_at`: ISO timestamp

### 10_raw_text_page_XXX.txt
Raw text extracted from each page of the PDF (before cleaning):
- `10_raw_text_page_001.txt`
- `10_raw_text_page_002.txt`
- etc.

### 20_clean_text.txt
Normalized and cleaned document text:
- Removes excessive whitespace
- Removes page numbers and headers/footers
- Normalizes line breaks
- Ready for analysis

### 30_chunks.jsonl
Document chunks with metadata (JSONL format):
```json
{
  "chunk_id": 1,
  "start_char": 0,
  "end_char": 1500,
  "text": "chunk content...",
  "length": 1500,
  "prev_chunk": null,
  "next_chunk": 2
}
```

### 35_rag_index.json
RAG indexing results with vector database information:
- `success`: Whether indexing completed successfully
- `count`: Total number of chunks processed
- `indexed`: Number of chunks successfully indexed
- `collection`: ChromaDB collection name ("policy_rules")
- `doc_id`: Document identifier (trace_id)
- `vectordb_dir`: Path to vector database storage
- `error`: Error message if indexing failed

### 40_llm_prompt.json
Exact data sent to the LLM:
- `provider`: LLM provider used
- `model`: Specific model
- `text_length`: Length of input text
- `text_preview`: First 500 characters
- `timestamp`: When sent
- `trace_id`: Associated trace

### 50_llm_response.json
Raw LLM response:
- `provider`: LLM provider
- `model`: Model used
- `result`: Parsed analysis result
- `timestamp`: When received
- `trace_id`: Associated trace
- `success`: Whether request succeeded

## API Endpoints

### Enable Tracing
```bash
POST /api/analyze?enable_tracing=true
```

### List All Traces
```bash
GET /api/traces
```

### Get Trace Details
```bash
GET /api/traces/{trace_id}
```

### Get Trace File
```bash
GET /api/traces/{trace_id}/files/{filename}
```

### Delete Trace
```bash
DELETE /api/traces/{trace_id}
```

### Cleanup Old Traces
```bash
POST /api/traces/cleanup?max_age_hours=24
```

## Frontend Integration

The frontend includes a Trace Viewer component that allows you to:
- Browse all available traces
- View trace metadata
- Inspect individual files
- View formatted JSON content
- Download trace files

## Usage Examples

### 1. Analyze with Tracing
```javascript
const response = await fetch('/api/analyze', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    file_path: '/path/to/document.pdf',
    analysis_method: 'llm',
    llm_provider: 'openai',
    model: 'gpt-4',
    fund_id: '5800'
  })
});

const { job_id, trace_id } = await response.json();
```

### 2. Inspect Trace Files
```javascript
// Get trace metadata
const trace = await fetch(`/api/traces/${trace_id}`).then(r => r.json());

// Get raw text from page 1
const page1 = await fetch(`/api/traces/${trace_id}/files/10_raw_text_page_001.txt`)
  .then(r => r.json());

// Get LLM response
const llmResponse = await fetch(`/api/traces/${trace_id}/files/50_llm_response.json`)
  .then(r => r.json());
```

### 3. Debug Analysis Issues
1. Find the trace_id from a failed analysis
2. Check `00_meta.json` for basic info
3. Review `10_raw_text_page_*.txt` to see if text extraction worked
4. Check `20_clean_text.txt` for text cleaning issues
5. Examine `40_llm_prompt.json` to see what was sent to the LLM
6. Review `50_llm_response.json` for LLM errors or unexpected responses

## Benefits

1. **Complete Traceability**: Every step is recorded
2. **Easy Debugging**: Quickly identify where issues occur
3. **Quality Assurance**: Verify analysis accuracy
4. **Performance Analysis**: Track timing at each stage
5. **Reproducibility**: Recreate exact conditions
6. **Audit Trail**: Maintain records for compliance

## File Management

- Traces are stored in the `traces/` directory
- Each trace gets a unique timestamp-based ID
- Old traces can be automatically cleaned up
- Individual traces can be deleted manually
- File sizes are tracked for monitoring

## Security Considerations

- Trace files may contain sensitive document content
- Ensure proper access controls on the traces directory
- Consider encryption for sensitive documents
- Implement retention policies for trace cleanup
- Monitor disk usage for trace storage
