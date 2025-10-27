from chromadb import PersistentClient
from typing import List, Dict, Any, Optional
import os
import json

# Try to import chromadb, fall back to mock if not available
try:
    from chromadb import PersistentClient
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    print("Warning: ChromaDB not available. RAG retrieval will use mock mode.")


def retrieve_rules(query: str, doc_id: str, k: int = 5, vectordb_dir: str = "/tmp/chroma") -> List[Dict[str, Any]]:
    """
    Retrieve top-k most relevant chunks for a decision item (sector, country, etc.)
    with bias toward chunks containing negations.
    
    Args:
        query: Search query (e.g., "Coal", "Saudi Arabia")
        doc_id: Document identifier to filter results
        k: Number of top results to return
        vectordb_dir: Directory containing ChromaDB storage
    
    Returns:
        List of dictionaries containing retrieved chunks with metadata
    """
    try:
        # Check if ChromaDB is available
        if not CHROMADB_AVAILABLE:
            return _retrieve_rules_mock(query, doc_id, k, vectordb_dir)
        
        # Real ChromaDB mode
        db = PersistentClient(path=vectordb_dir)
        coll = db.get_collection("policy_rules")
        
        # Query with more results than needed for reranking
        res = coll.query(
            query_texts=[query],
            n_results=k * 2,  # Get more results for reranking
            where={"doc_id": doc_id}
        )
        
        # Check if we got any results
        if not res["ids"] or not res["ids"][0]:
            return []
        
        # Build items list with all available data
        items = []
        for i in range(len(res["ids"][0])):
            item = {
                "id": res["ids"][0][i],
                "text": res["documents"][0][i],
                "meta": res["metadatas"][0][i],
                "distance": res["distances"][0][i] if res["distances"] and res["distances"][0] else 1.0
            }
            items.append(item)
        
        # Rerank: prefer negation-bearing chunks, then by distance (shorter chunks first)
        items.sort(key=lambda x: (
            not x["meta"].get("has_negation", False),  # Negation chunks first
            x["meta"].get("char_len", 1)  # Then shorter chunks (crisper rules)
        ))
        
        return items[:k]
        
    except Exception as e:
        print(f"Error in retrieve_rules: {e}")
        return []


def _retrieve_rules_mock(query: str, doc_id: str, k: int = 5, vectordb_dir: str = "/tmp/chroma") -> List[Dict[str, Any]]:
    """
    Mock implementation of retrieve_rules using simple text search
    """
    try:
        # Look for index files in the vectordb directory
        index_files = []
        if os.path.exists(vectordb_dir):
            for file in os.listdir(vectordb_dir):
                if file.endswith("_index.json"):
                    index_files.append(os.path.join(vectordb_dir, file))
        
        all_items = []
        
        for index_file in index_files:
            with open(index_file, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            
            # Filter by doc_id if specified
            if doc_id and index_data.get("doc_id") != doc_id:
                continue
            
            # Simple text search with relevance scoring
            query_lower = query.lower()
            for i, (doc, meta) in enumerate(zip(index_data["documents"], index_data["metadatas"])):
                if query_lower in doc.lower():
                    # Simple relevance scoring based on query word frequency
                    relevance = doc.lower().count(query_lower) / len(doc.split())
                    
                    item = {
                        "id": index_data["ids"][i],
                        "text": doc,
                        "meta": meta,
                        "distance": 1 - relevance
                    }
                    all_items.append(item)
        
        # Rerank: prefer negation-bearing chunks, then by relevance
        all_items.sort(key=lambda x: (
            not x["meta"].get("has_negation", False),  # Negation chunks first
            x["meta"].get("char_len", 1)  # Then shorter chunks
        ))
        
        return all_items[:k]
        
    except Exception as e:
        print(f"Error in _retrieve_rules_mock: {e}")
        return []


def retrieve_rules_batch(queries: List[str], doc_id: str, k: int = 5, vectordb_dir: str = "/tmp/chroma") -> Dict[str, List[Dict[str, Any]]]:
    """
    Retrieve rules for multiple decision items in batch
    
    Args:
        queries: List of search queries (e.g., ["Coal", "Saudi Arabia", "Renewable Energy"])
        doc_id: Document identifier to filter results
        k: Number of top results to return per query
        vectordb_dir: Directory containing ChromaDB storage
    
    Returns:
        Dictionary mapping each query to its retrieved chunks
    """
    results = {}
    
    for query in queries:
        results[query] = retrieve_rules(query, doc_id, k, vectordb_dir)
    
    return results


def get_negation_chunks(query: str, doc_id: str, k: int = 5, vectordb_dir: str = "/tmp/chroma") -> List[Dict[str, Any]]:
    """
    Retrieve only chunks that contain negations for a given query
    
    Args:
        query: Search query
        doc_id: Document identifier to filter results
        k: Number of top results to return
        vectordb_dir: Directory containing ChromaDB storage
    
    Returns:
        List of negation-bearing chunks
    """
    # Get more results to filter for negations
    all_results = retrieve_rules(query, doc_id, k * 3, vectordb_dir)
    
    # Filter for negation chunks only
    negation_chunks = [
        item for item in all_results 
        if item["meta"].get("has_negation", False)
    ]
    
    return negation_chunks[:k]


def get_chunk_by_id(chunk_id: str, vectordb_dir: str = "/tmp/chroma") -> Optional[Dict[str, Any]]:
    """
    Retrieve a specific chunk by its ID
    
    Args:
        chunk_id: Unique chunk identifier
        vectordb_dir: Directory containing ChromaDB storage
    
    Returns:
        Chunk data if found, None otherwise
    """
    try:
        if not CHROMADB_AVAILABLE:
            return _get_chunk_by_id_mock(chunk_id, vectordb_dir)
        
        # Real ChromaDB mode
        db = PersistentClient(path=vectordb_dir)
        coll = db.get_collection("policy_rules")
        
        result = coll.get(ids=[chunk_id])
        
        if result["ids"] and result["ids"][0]:
            return {
                "id": result["ids"][0],
                "text": result["documents"][0],
                "meta": result["metadatas"][0]
            }
        
        return None
        
    except Exception as e:
        print(f"Error in get_chunk_by_id: {e}")
        return None


def _get_chunk_by_id_mock(chunk_id: str, vectordb_dir: str = "/tmp/chroma") -> Optional[Dict[str, Any]]:
    """Mock implementation of get_chunk_by_id"""
    try:
        if os.path.exists(vectordb_dir):
            for file in os.listdir(vectordb_dir):
                if file.endswith("_index.json"):
                    file_path = os.path.join(vectordb_dir, file)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        index_data = json.load(f)
                    
                    # Search for the chunk ID
                    if chunk_id in index_data.get("ids", []):
                        idx = index_data["ids"].index(chunk_id)
                        return {
                            "id": index_data["ids"][idx],
                            "text": index_data["documents"][idx],
                            "meta": index_data["metadatas"][idx]
                        }
        
        return None
        
    except Exception as e:
        print(f"Error in _get_chunk_by_id_mock: {e}")
        return None
