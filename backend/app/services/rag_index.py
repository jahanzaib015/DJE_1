from openai import OpenAI
from pathlib import Path
import json
import re
import hashlib
import os
from typing import Dict, List, Any, Optional

# Try to import chromadb, fall back to mock if not available
try:
    from chromadb import PersistentClient
    from chromadb.utils import embedding_functions
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    print("Warning: ChromaDB not available. RAG indexing will use mock mode.")

# Initialize OpenAI client only if API key is available
try:
    client = OpenAI()
    OPENAI_AVAILABLE = True
except Exception:
    client = None
    OPENAI_AVAILABLE = False
    print("Warning: OpenAI API key not found. Embedding generation will be disabled.")

NEG_CUES = r"\b(not|no|except|unless|excluded|exclusion|prohibit|forbidden|restricted|ban(?:ned)?)\b"

def sha1(s: str) -> str:
    """Generate SHA1 hash of string"""
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def detect_flags(text: str) -> Dict[str, Any]:
    """Detect flags in text like negation cues"""
    has_neg = bool(re.search(NEG_CUES, text, flags=re.I))
    return {"has_negation": has_neg, "char_len": len(text)}

def embed(texts: List[str]) -> List[List[float]]:
    """Generate embeddings using OpenAI text-embedding-3-large"""
    if not OPENAI_AVAILABLE or not client:
        # Return mock embeddings (random vectors)
        import random
        return [[random.random() for _ in range(1536)] for _ in texts]
    
    resp = client.embeddings.create(model="text-embedding-3-large", input=texts)
    return [d.embedding for d in resp.data]

def index_pdf(clean_text_path: str, chunks_path: str, vectordb_dir: str, doc_id: str) -> Dict[str, Any]:
    """
    Index PDF chunks into ChromaDB for RAG retrieval
    
    Args:
        clean_text_path: Path to cleaned text file (20_clean_text.txt)
        chunks_path: Path to chunks JSONL file (30_chunks.jsonl)
        vectordb_dir: Directory for ChromaDB storage
        doc_id: Unique document identifier (trace_id)
    
    Returns:
        Dictionary with indexing results
    """
    try:
        # Read clean text
        clean_text = Path(clean_text_path).read_text(encoding="utf-8")
        
        # Read chunks from JSONL
        chunks = []
        with open(chunks_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    chunks.append(json.loads(line))
        
        # Prepare documents to upsert
        documents, metadatas, ids = [], [], []
        
        for i, ch in enumerate(chunks):
            # Handle both dict and string chunk formats
            if isinstance(ch, dict):
                text = ch.get("text", "")
                meta = {
                    "doc_id": doc_id,
                    "chunk_idx": i,
                    "span_start": ch.get("span", [None, None])[0],
                    "span_end": ch.get("span", [None, None])[1],
                    "page": ch.get("page"),
                    "chunk_id": ch.get("chunk_id"),
                    "start_char": ch.get("start_char"),
                    "end_char": ch.get("end_char"),
                    "length": ch.get("length"),
                    "prev_chunk": ch.get("prev_chunk"),
                    "next_chunk": ch.get("next_chunk"),
                    **detect_flags(text)
                }
            else:
                # Fallback for string chunks
                text = str(ch)
                meta = {
                    "doc_id": doc_id,
                    "chunk_idx": i,
                    "span_start": None,
                    "span_end": None,
                    "page": None,
                    "chunk_id": i,
                    "start_char": None,
                    "end_char": None,
                    "length": len(text),
                    "prev_chunk": i - 1 if i > 0 else None,
                    "next_chunk": i + 1 if i < len(chunks) - 1 else None,
                    **detect_flags(text)
                }
            
            documents.append(text)
            metadatas.append(meta)
            ids.append(f"{doc_id}_{i}_{sha1(text)[:8]}")
        
        # Check if ChromaDB is available
        if not CHROMADB_AVAILABLE:
            # Mock mode - just save the processed data
            os.makedirs(vectordb_dir, exist_ok=True)
            
            # Save processed chunks as JSON for later retrieval
            mock_index_path = os.path.join(vectordb_dir, f"{doc_id}_index.json")
            mock_data = {
                "doc_id": doc_id,
                "chunks": chunks,
                "documents": documents,
                "metadatas": metadatas,
                "ids": ids,
                "created_at": str(Path().cwd()),
                "mode": "mock"
            }
            
            with open(mock_index_path, 'w', encoding='utf-8') as f:
                json.dump(mock_data, f, indent=2, ensure_ascii=False)
            
            return {
                "success": True,
                "count": len(documents),
                "indexed": len(documents),
                "collection": "policy_rules",
                "doc_id": doc_id,
                "vectordb_dir": vectordb_dir,
                "mode": "mock",
                "index_file": mock_index_path
            }
        
        # Real ChromaDB mode
        # Ensure vector database directory exists
        os.makedirs(vectordb_dir, exist_ok=True)
        
        # Create / open collection
        db = PersistentClient(path=vectordb_dir)
        coll = db.get_or_create_collection(
            name="policy_rules",
            embedding_function=embedding_functions.OpenAIEmbeddingFunction(
                api_key=None,  # Will use OPENAI_API_KEY from environment
                model_name="text-embedding-3-large"
            )
        )
        
        # Compute embeddings in batches to control rate
        BATCH_SIZE = 64
        total_indexed = 0
        
        for s in range(0, len(documents), BATCH_SIZE):
            batch_docs = documents[s:s+BATCH_SIZE]
            batch_ids = ids[s:s+BATCH_SIZE]
            batch_meta = metadatas[s:s+BATCH_SIZE]
            
            # Generate embeddings
            vecs = embed(batch_docs)
            
            # Upsert with precomputed embeddings
            coll.upsert(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_meta,
                embeddings=vecs
            )
            
            total_indexed += len(batch_docs)
        
        return {
            "success": True,
            "count": len(documents),
            "indexed": total_indexed,
            "collection": "policy_rules",
            "doc_id": doc_id,
            "vectordb_dir": vectordb_dir,
            "mode": "chromadb"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "count": 0,
            "indexed": 0,
            "collection": "policy_rules",
            "doc_id": doc_id
        }

def query_rag(vectordb_dir: str, query: str, n_results: int = 5, doc_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Query the RAG index for relevant chunks
    
    Args:
        vectordb_dir: Directory containing ChromaDB
        query: Search query
        n_results: Number of results to return
        doc_id: Optional document ID to filter results
    
    Returns:
        Dictionary with query results
    """
    try:
        # Check if ChromaDB is available
        if not CHROMADB_AVAILABLE:
            # Mock mode - simple text search
            return _query_rag_mock(vectordb_dir, query, n_results, doc_id)
        
        # Real ChromaDB mode
        # Open collection
        db = PersistentClient(path=vectordb_dir)
        coll = db.get_collection("policy_rules")
        
        # Build where clause for document filtering
        where_clause = {}
        if doc_id:
            where_clause["doc_id"] = doc_id
        
        # Query collection
        results = coll.query(
            query_texts=[query],
            n_results=n_results,
            where=where_clause if where_clause else None
        )
        
        # Format results
        formatted_results = []
        if results['documents'] and results['documents'][0]:
            for i, (doc, meta, dist) in enumerate(zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            )):
                formatted_results.append({
                    "rank": i + 1,
                    "text": doc,
                    "metadata": meta,
                    "distance": dist,
                    "relevance_score": 1 - dist  # Convert distance to relevance
                })
        
        return {
            "success": True,
            "query": query,
            "results": formatted_results,
            "total_results": len(formatted_results),
            "mode": "chromadb"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "query": query,
            "results": [],
            "total_results": 0
        }

def _query_rag_mock(vectordb_dir: str, query: str, n_results: int = 5, doc_id: Optional[str] = None) -> Dict[str, Any]:
    """Mock RAG query using simple text search"""
    try:
        # Look for index files in the vectordb directory
        index_files = []
        if os.path.exists(vectordb_dir):
            for file in os.listdir(vectordb_dir):
                if file.endswith("_index.json"):
                    index_files.append(os.path.join(vectordb_dir, file))
        
        all_results = []
        
        for index_file in index_files:
            with open(index_file, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            
            # Filter by doc_id if specified
            if doc_id and index_data.get("doc_id") != doc_id:
                continue
            
            # Simple text search
            query_lower = query.lower()
            for i, (doc, meta) in enumerate(zip(index_data["documents"], index_data["metadatas"])):
                if query_lower in doc.lower():
                    # Simple relevance scoring based on query word frequency
                    relevance = doc.lower().count(query_lower) / len(doc.split())
                    all_results.append({
                        "rank": len(all_results) + 1,
                        "text": doc,
                        "metadata": meta,
                        "distance": 1 - relevance,
                        "relevance_score": relevance
                    })
        
        # Sort by relevance and limit results
        all_results.sort(key=lambda x: x["relevance_score"], reverse=True)
        formatted_results = all_results[:n_results]
        
        return {
            "success": True,
            "query": query,
            "results": formatted_results,
            "total_results": len(formatted_results),
            "mode": "mock"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "query": query,
            "results": [],
            "total_results": 0,
            "mode": "mock"
        }

def get_collection_stats(vectordb_dir: str) -> Dict[str, Any]:
    """Get statistics about the indexed collection"""
    try:
        # Check if ChromaDB is available
        if not CHROMADB_AVAILABLE:
            # Mock mode - count index files
            return _get_collection_stats_mock(vectordb_dir)
        
        # Real ChromaDB mode
        db = PersistentClient(path=vectordb_dir)
        coll = db.get_collection("policy_rules")
        
        count = coll.count()
        
        # Get unique document IDs
        results = coll.get(include=['metadatas'])
        doc_ids = set()
        if results['metadatas']:
            for meta in results['metadatas']:
                if 'doc_id' in meta:
                    doc_ids.add(meta['doc_id'])
        
        return {
            "success": True,
            "total_chunks": count,
            "unique_documents": len(doc_ids),
            "document_ids": list(doc_ids),
            "mode": "chromadb"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "total_chunks": 0,
            "unique_documents": 0,
            "document_ids": []
        }

def _get_collection_stats_mock(vectordb_dir: str) -> Dict[str, Any]:
    """Mock collection stats by counting index files"""
    try:
        total_chunks = 0
        doc_ids = set()
        
        if os.path.exists(vectordb_dir):
            for file in os.listdir(vectordb_dir):
                if file.endswith("_index.json"):
                    file_path = os.path.join(vectordb_dir, file)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        index_data = json.load(f)
                    
                    doc_ids.add(index_data.get("doc_id", "unknown"))
                    total_chunks += len(index_data.get("documents", []))
        
        return {
            "success": True,
            "total_chunks": total_chunks,
            "unique_documents": len(doc_ids),
            "document_ids": list(doc_ids),
            "mode": "mock"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "total_chunks": 0,
            "unique_documents": 0,
            "document_ids": [],
            "mode": "mock"
        }
