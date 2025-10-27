# RAG Indexing Documentation

## Overview

The RAG (Retrieval-Augmented Generation) indexing system automatically processes PDF documents and creates a searchable vector database for semantic search and retrieval.

## How It Works

### 1. Automatic Indexing
When a PDF is processed through the analysis pipeline, the system automatically:
- Extracts and cleans text from the PDF
- Creates semantic chunks with metadata
- Generates vector embeddings using OpenAI's `text-embedding-3-large`
- Stores everything in a ChromaDB vector database

### 2. Indexing Process
The indexing happens right after text chunking in the pipeline:
```
PDF Upload → Text Extraction → Chunking → RAG Indexing → Analysis
```

### 3. Vector Database Structure
- **Collection Name**: `policy_rules`
- **Storage Location**: `var/chroma/` (local) or configured path
- **Embeddings**: 1536-dimensional vectors from OpenAI
- **Metadata**: Document ID, chunk info, negation flags, page numbers

## API Endpoints

### Query RAG Index
```http
POST /api/rag/query
Content-Type: application/json

{
  "query": "investment objectives",
  "n_results": 5,
  "doc_id": "optional_trace_id"
}
```

**Response:**
```json
{
  "success": true,
  "query": "investment objectives",
  "results": [
    {
      "rank": 1,
      "text": "The fund shall invest primarily in equity securities...",
      "metadata": {
        "doc_id": "trace_123",
        "chunk_idx": 0,
        "page": 1,
        "has_negation": false
      },
      "relevance_score": 0.95
    }
  ],
  "total_results": 1,
  "mode": "chromadb"
}
```

### Get Collection Statistics
```http
GET /api/rag/stats
```

**Response:**
```json
{
  "success": true,
  "total_chunks": 150,
  "unique_documents": 5,
  "document_ids": ["trace_123", "trace_456"],
  "mode": "chromadb"
}
```

## Trace Files

Each processed document creates a trace with RAG indexing results:

### 35_rag_index.json
```json
{
  "success": true,
  "count": 25,
  "indexed": 25,
  "collection": "policy_rules",
  "doc_id": "trace_123",
  "vectordb_dir": "var/chroma",
  "mode": "chromadb"
}
```

## Production vs Development

### Production (Render)
- ✅ Full ChromaDB vector database
- ✅ OpenAI embeddings for semantic search
- ✅ High-quality similarity matching
- ✅ Persistent storage

### Local Development
- ⚠️ Mock mode with simple text search (if ChromaDB not installed)
- ⚠️ No vector embeddings (just keyword matching)
- ✅ Still processes and indexes documents

## Requirements

### Production Dependencies
- `chromadb==0.4.24` (added to requirements.txt)
- OpenAI API key configured
- Sufficient disk space for vector storage

### Local Development
- Microsoft Visual C++ Build Tools (for ChromaDB compilation)
- Or use mock mode for testing

## Usage Examples

### 1. Basic Query
```python
import requests

response = requests.post("http://your-api/api/rag/query", 
    json={"query": "risk management", "n_results": 3})
results = response.json()
```

### 2. Document-Specific Query
```python
response = requests.post("http://your-api/api/rag/query", 
    json={
        "query": "investment guidelines", 
        "n_results": 5,
        "doc_id": "trace_123"
    })
```

### 3. Check Index Status
```python
response = requests.get("http://your-api/api/rag/stats")
stats = response.json()
print(f"Total chunks indexed: {stats['total_chunks']}")
```

## Benefits

1. **Semantic Search**: Find relevant content even with different wording
2. **Contextual Retrieval**: Get chunks that are semantically related to your query
3. **Metadata Filtering**: Search within specific documents or pages
4. **Scalable**: Handles large document collections efficiently
5. **Integration**: Seamlessly integrated into existing PDF processing pipeline

## Next Steps

The RAG indexing is now fully integrated into your PDF processing pipeline. Every document you process will be automatically indexed and searchable through the API endpoints.
