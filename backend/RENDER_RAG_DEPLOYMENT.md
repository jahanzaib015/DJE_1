# RAG Retrieval Deployment on Render

This guide covers deploying the RAG retrieval functionality on Render with focus on decision item analysis.

## Overview

The RAG retrieval system is now configured for Render deployment with:
- ChromaDB vector database using `/tmp/chroma` directory
- Decision item retrieval with negation bias
- Batch processing for multiple queries
- Render-compatible API endpoints

## Deployment Configuration

### 1. Requirements
The `requirements_render.txt` includes all necessary dependencies:
- `chromadb==0.4.24` - Vector database
- `PyMuPDF==1.23.8` - PDF processing
- `nltk==3.8.1` - Text processing

### 2. Directory Structure
- Vector database: `/tmp/chroma` (Render-compatible)
- Index files: `/tmp/chroma/*_index.json` (mock mode fallback)

### 3. API Endpoints

#### Single Query Retrieval
```bash
POST /api/rag/retrieve
Parameters:
- query: string (e.g., "Coal", "Saudi Arabia")
- doc_id: string (document identifier)
- k: int (number of results, default: 5)
```

#### Batch Retrieval
```bash
POST /api/rag/retrieve/batch
Parameters:
- queries: list (e.g., ["Coal", "Oil", "Renewable Energy"])
- doc_id: string (document identifier)
- k: int (number of results per query, default: 5)
```

#### Negation-Only Retrieval
```bash
POST /api/rag/negations
Parameters:
- query: string (decision item)
- doc_id: string (document identifier)
- k: int (number of results, default: 5)
```

#### RAG Statistics
```bash
GET /api/rag/stats
Returns collection statistics and document counts
```

## Testing on Render

### 1. Using the Test Script
```bash
# Update the RENDER_URL in test_render_rag.py
python test_render_rag.py
```

### 2. Using curl Commands
```bash
# Test single query
curl -X POST "https://your-app.onrender.com/api/rag/retrieve?query=Coal&doc_id=trace_123&k=3"

# Test batch query
curl -X POST "https://your-app.onrender.com/api/rag/retrieve/batch?queries=[\"Coal\",\"Saudi Arabia\"]&doc_id=trace_123&k=2"

# Test negation retrieval
curl -X POST "https://your-app.onrender.com/api/rag/negations?query=Fossil%20Fuels&doc_id=trace_123&k=3"

# Get stats
curl -X GET "https://your-app.onrender.com/api/rag/stats"
```

### 3. Using Python requests
```python
import requests

# Single query
response = requests.post(
    "https://your-app.onrender.com/api/rag/retrieve",
    params={"query": "Coal", "doc_id": "trace_123", "k": 3}
)
print(response.json())

# Batch query
response = requests.post(
    "https://your-app.onrender.com/api/rag/retrieve/batch",
    params={
        "queries": ["Coal", "Oil", "Renewable Energy"],
        "doc_id": "trace_123",
        "k": 2
    }
)
print(response.json())
```

## Key Features for Render

### 1. Negation-Aware Retrieval
- Automatically prioritizes chunks with restriction language
- Reranks results to surface compliance constraints
- Perfect for analyzing investment restrictions

### 2. Decision Item Focus
- Designed for sectors, countries, investment types
- Filters by document ID for targeted analysis
- Returns structured metadata for each chunk

### 3. Render Compatibility
- Uses `/tmp/chroma` directory (writable on Render)
- Graceful fallback to mock mode if ChromaDB fails
- Optimized for Render's ephemeral filesystem

### 4. Batch Processing
- Efficient handling of multiple decision items
- Reduces API calls for bulk analysis
- Maintains individual result sets per query

## Response Format

### Single Query Response
```json
{
  "success": true,
  "query": "Coal",
  "doc_id": "trace_123",
  "k": 3,
  "results": [
    {
      "id": "chunk_id_1",
      "text": "The fund may not invest in coal companies...",
      "meta": {
        "has_negation": true,
        "char_len": 150,
        "page": 5,
        "doc_id": "trace_123"
      },
      "distance": 0.2
    }
  ],
  "count": 3
}
```

### Batch Query Response
```json
{
  "success": true,
  "queries": ["Coal", "Oil"],
  "doc_id": "trace_123",
  "k": 2,
  "results": {
    "Coal": [...],
    "Oil": [...]
  },
  "total_queries": 2
}
```

## Error Handling

The system includes comprehensive error handling:
- Graceful fallback to mock mode if ChromaDB unavailable
- Detailed error messages for debugging
- HTTP status codes for different error types

## Performance Considerations

- Vector database stored in `/tmp/chroma` (fast access)
- Batch processing reduces individual API calls
- Reranking optimized for negation detection
- Mock mode ensures functionality even without ChromaDB

## Monitoring

Use the `/api/rag/stats` endpoint to monitor:
- Total chunks indexed
- Number of unique documents
- Database mode (chromadb/mock)
- Collection health

## Troubleshooting

### Common Issues
1. **ChromaDB not available**: System falls back to mock mode
2. **No results found**: Check document ID and query terms
3. **Empty responses**: Verify document has been indexed

### Debug Steps
1. Check `/api/rag/stats` for collection status
2. Verify document ID exists in traces
3. Test with simple queries first
4. Check Render logs for errors

## Integration with Existing System

The RAG retrieval integrates seamlessly with:
- Existing analysis service
- Document processing pipeline
- Trace management system
- WebSocket real-time updates

This provides a complete solution for decision item analysis with bias toward restriction-bearing content, optimized for Render deployment.
