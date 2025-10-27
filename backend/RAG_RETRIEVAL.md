# RAG Retrieval Module

This module provides retrieval functionality for decision items (sectors, countries, etc.) with bias toward negation-bearing chunks for compliance analysis.

## Overview

The `rag_retrieve.py` module implements intelligent retrieval that:
- Fetches top-k most relevant chunks for each decision item
- Prioritizes chunks containing negations (restrictions, prohibitions)
- Supports both ChromaDB and mock modes for development
- Provides batch processing for multiple decision items

## Key Features

### 1. Negation-Aware Retrieval
- Automatically detects chunks with negation cues (not, no, except, unless, etc.)
- Reranks results to prioritize restriction-bearing content
- Helps identify compliance constraints and prohibitions

### 2. Decision Item Focus
- Designed for analyzing specific sectors, countries, or investment types
- Filters results by document ID for targeted analysis
- Returns structured metadata for each retrieved chunk

### 3. Flexible Integration
- Works with existing ChromaDB infrastructure
- Falls back to mock mode when ChromaDB unavailable
- Compatible with existing analysis service patterns

## API Reference

### Core Functions

#### `retrieve_rules(query, doc_id, k=5, vectordb_dir="var/chroma")`
Retrieve top-k most relevant chunks for a decision item.

**Parameters:**
- `query` (str): Search query (e.g., "Coal", "Saudi Arabia")
- `doc_id` (str): Document identifier to filter results
- `k` (int): Number of top results to return (default: 5)
- `vectordb_dir` (str): ChromaDB storage directory (default: "var/chroma")

**Returns:**
- List of dictionaries containing:
  - `id`: Unique chunk identifier
  - `text`: Chunk content
  - `meta`: Metadata including negation flags and character length
  - `distance`: Similarity distance score

#### `retrieve_rules_batch(queries, doc_id, k=5, vectordb_dir="var/chroma")`
Retrieve rules for multiple decision items in batch.

**Parameters:**
- `queries` (List[str]): List of search queries
- `doc_id` (str): Document identifier
- `k` (int): Number of results per query
- `vectordb_dir` (str): ChromaDB storage directory

**Returns:**
- Dictionary mapping each query to its retrieved chunks

#### `get_negation_chunks(query, doc_id, k=5, vectordb_dir="var/chroma")`
Retrieve only chunks that contain negations for a given query.

**Parameters:**
- `query` (str): Search query
- `doc_id` (str): Document identifier
- `k` (int): Number of results to return
- `vectordb_dir` (str): ChromaDB storage directory

**Returns:**
- List of negation-bearing chunks

#### `get_chunk_by_id(chunk_id, vectordb_dir="var/chroma")`
Retrieve a specific chunk by its ID.

**Parameters:**
- `chunk_id` (str): Unique chunk identifier
- `vectordb_dir` (str): ChromaDB storage directory

**Returns:**
- Chunk data if found, None otherwise

## Usage Examples

### Basic Retrieval
```python
from services.rag_retrieve import retrieve_rules

# Retrieve rules for coal sector
coal_chunks = retrieve_rules("Coal", "trace_123", k=5)

for chunk in coal_chunks:
    print(f"Text: {chunk['text'][:100]}...")
    print(f"Has Negation: {chunk['meta'].get('has_negation', False)}")
    print(f"Length: {chunk['meta'].get('char_len', 0)} chars")
```

### Batch Processing
```python
from services.rag_retrieve import retrieve_rules_batch

# Analyze multiple sectors
sectors = ["Coal", "Oil", "Renewable Energy"]
results = retrieve_rules_batch(sectors, "trace_123", k=3)

for sector, chunks in results.items():
    print(f"{sector}: {len(chunks)} chunks found")
```

### Negation-Focused Analysis
```python
from services.rag_retrieve import get_negation_chunks

# Find restriction patterns
restrictions = get_negation_chunks("Fossil Fuels", "trace_123", k=5)

for chunk in restrictions:
    print(f"Restriction: {chunk['text']}")
```

## Integration with Analysis Service

The RAG retrieval module can be integrated with the existing analysis service to pre-filter content:

```python
from services.rag_retrieve import retrieve_rules
from services.analysis_service import AnalysisService

# Pre-filter content using RAG
decision_items = ["Coal", "Saudi Arabia", "Renewable Energy"]
relevant_chunks = []

for item in decision_items:
    chunks = retrieve_rules(item, doc_id, k=2)
    relevant_chunks.extend(chunks)

# Combine for analysis
combined_text = "\n\n".join([chunk['text'] for chunk in relevant_chunks])

# Analyze with existing service
analysis_service = AnalysisService()
result = await analysis_service.analyze_document(
    text=combined_text,
    analysis_method=AnalysisMethod.LLM,
    llm_provider=LLMProvider.OPENAI,
    model="gpt-4",
    fund_id="example_fund"
)
```

## Reranking Algorithm

The module uses a two-tier reranking approach:

1. **Negation Priority**: Chunks with negation cues are ranked first
2. **Length Priority**: Among chunks with same negation status, shorter chunks are preferred (crisper rules)

This ensures that restriction-bearing content is prioritized while maintaining relevance.

## Error Handling

- Graceful fallback to mock mode when ChromaDB unavailable
- Comprehensive error logging for debugging
- Returns empty lists on failure rather than crashing

## Testing

Run the test suite to verify functionality:

```bash
cd backend
python test_rag_retrieve.py
```

Run integration examples:

```bash
cd backend
python example_rag_integration.py
```

## Dependencies

- `chromadb`: Vector database for similarity search
- `json`: For mock mode data handling
- `os`: For file system operations
- `typing`: For type hints

## Configuration

The module respects the existing ChromaDB configuration from `rag_index.py`:
- Uses the same collection name ("policy_rules")
- Supports the same embedding function (text-embedding-3-large)
- Maintains compatibility with existing index structure
