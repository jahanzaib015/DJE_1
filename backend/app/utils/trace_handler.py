import os
import json
import uuid
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
import aiofiles
from pathlib import Path

class TraceHandler:
    """Handles forensic tracing for document analysis pipeline"""
    
    def __init__(self, trace_id: str = None, base_traces_dir: str = "traces"):
        self.trace_id = trace_id
        self.base_traces_dir = base_traces_dir
        self._ensure_traces_directory()
    
    def _ensure_traces_directory(self):
        """Ensure traces directory exists"""
        os.makedirs(self.base_traces_dir, exist_ok=True)
    
    def generate_trace_id(self) -> str:
        """Generate unique trace ID"""
        return f"trace_{int(time.time())}_{str(uuid.uuid4())[:8]}"
    
    def get_trace_dir(self, trace_id: str) -> str:
        """Get trace directory path"""
        return os.path.join(self.base_traces_dir, trace_id)
    
    async def create_trace_directory(self, trace_id: str) -> str:
        """Create trace directory and return path"""
        trace_dir = self.get_trace_dir(trace_id)
        os.makedirs(trace_dir, exist_ok=True)
        return trace_dir
    
    async def save_meta(self, trace_id: str, meta_data: Dict[str, Any]) -> str:
        """Save 00_meta.json with metadata"""
        trace_dir = self.get_trace_dir(trace_id)
        meta_path = os.path.join(trace_dir, "00_meta.json")
        
        async with aiofiles.open(meta_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(meta_data, indent=2, ensure_ascii=False))
        
        return meta_path
    
    async def save_raw_text_page(self, trace_id: str, page_num: int, text: str) -> str:
        """Save 10_raw_text_page_XXX.txt for each page"""
        trace_dir = self.get_trace_dir(trace_id)
        page_filename = f"10_raw_text_page_{page_num:03d}.txt"
        page_path = os.path.join(trace_dir, page_filename)
        
        async with aiofiles.open(page_path, 'w', encoding='utf-8') as f:
            await f.write(text)
        
        return page_path
    
    async def save_clean_text(self, trace_id: str, clean_text: str) -> str:
        """Save 20_clean_text.txt with normalized document text"""
        trace_dir = self.get_trace_dir(trace_id)
        clean_path = os.path.join(trace_dir, "20_clean_text.txt")
        
        async with aiofiles.open(clean_path, 'w', encoding='utf-8') as f:
            await f.write(clean_text)
        
        return clean_path
    
    async def save_chunks(self, trace_id: str, chunks: List[Dict[str, Any]]) -> str:
        """Save 30_chunks.jsonl with document chunks"""
        trace_dir = self.get_trace_dir(trace_id)
        chunks_path = os.path.join(trace_dir, "30_chunks.jsonl")
        
        async with aiofiles.open(chunks_path, 'w', encoding='utf-8') as f:
            for chunk in chunks:
                await f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
        
        return chunks_path
    
    async def save_llm_prompt(self, trace_id: str, prompt_data: Dict[str, Any]) -> str:
        """Save 40_llm_prompt.json with exact LLM messages"""
        trace_dir = self.get_trace_dir(trace_id)
        prompt_path = os.path.join(trace_dir, "40_llm_prompt.json")
        
        async with aiofiles.open(prompt_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(prompt_data, indent=2, ensure_ascii=False))
        
        return prompt_path
    
    async def save_llm_response(self, trace_id: str, response_data: Dict[str, Any]) -> str:
        """Save 50_llm_response.json with raw LLM response"""
        trace_dir = self.get_trace_dir(trace_id)
        response_path = os.path.join(trace_dir, "50_llm_response.json")
        
        async with aiofiles.open(response_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(response_data, indent=2, ensure_ascii=False))
        
        return response_path
    
    async def save_tables(self, trace_id: str, tables: List[Dict[str, Any]]) -> str:
        """Save 25_tables.json with extracted table data"""
        trace_dir = self.get_trace_dir(trace_id)
        tables_path = os.path.join(trace_dir, "25_tables.json")
        
        async with aiofiles.open(tables_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(tables, indent=2, ensure_ascii=False))
        
        return tables_path
    
    async def save_rag_index(self, trace_id: str, rag_results: Dict[str, Any]) -> str:
        """Save 35_rag_index.json with RAG indexing results"""
        trace_dir = self.get_trace_dir(trace_id)
        rag_path = os.path.join(trace_dir, "35_rag_index.json")
        
        async with aiofiles.open(rag_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(rag_results, indent=2, ensure_ascii=False))
        
        return rag_path
    
    async def log_retrieval(self, trace_id: str, retrieved_chunks: List[Dict[str, Any]]) -> str:
        """Log retrieval results with chunk scoring and metadata"""
        trace_dir = self.get_trace_dir(trace_id)
        retrieval_path = os.path.join(trace_dir, "60_retrieval_log.json")
        
        # Extract relevant information for logging
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "retrieved_chunks": [
                {
                    "page": chunk.get("page"),
                    "score": chunk.get("relevance_score", chunk.get("distance", 0)),
                    "type": chunk.get("type", chunk.get("meta", {}).get("type", "unknown")),
                    "chunk_id": chunk.get("chunk_id", chunk.get("id")),
                    "source": chunk.get("source", chunk.get("meta", {}).get("source", "unknown")),
                    "has_negations": chunk.get("has_negations", chunk.get("meta", {}).get("has_negation", False)),
                    "length": chunk.get("length", len(chunk.get("text", ""))),
                    "text_preview": chunk.get("text", "")[:200] + "..." if len(chunk.get("text", "")) > 200 else chunk.get("text", "")
                }
                for chunk in retrieved_chunks
            ],
            "total_chunks": len(retrieved_chunks),
            "chunk_types": {
                "text": len([c for c in retrieved_chunks if c.get("type", c.get("meta", {}).get("type", "")) == "text"]),
                "table": len([c for c in retrieved_chunks if c.get("type", c.get("meta", {}).get("type", "")) == "table"])
            }
        }
        
        async with aiofiles.open(retrieval_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(log_data, indent=2, ensure_ascii=False))
        
        return retrieval_path
    
    def save_trace(self, trace_id: str, log_data: Dict[str, Any]) -> str:
        """Save general trace data (synchronous version for compatibility)"""
        trace_dir = self.get_trace_dir(trace_id)
        os.makedirs(trace_dir, exist_ok=True)
        
        # Add timestamp if not present
        if "timestamp" not in log_data:
            log_data["timestamp"] = datetime.now().isoformat()
        
        # Save to general trace log
        trace_log_path = os.path.join(trace_dir, "99_trace_log.json")
        
        # Load existing log data if it exists
        existing_data = {}
        if os.path.exists(trace_log_path):
            try:
                with open(trace_log_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                existing_data = {}
        
        # Merge new data with existing
        existing_data.update(log_data)
        
        with open(trace_log_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
        
        return trace_log_path
    
    def log_step(self, step_name: str, data: dict):
        """Log a processing step with timestamp"""
        if not self.trace_id:
            raise ValueError("TraceHandler must be initialized with trace_id to use log_step")
        
        # Create step entry
        step_entry = {"timestamp": datetime.now().isoformat(), "step": step_name, "data": data}
        
        # Load existing trace data
        trace_dir = self.get_trace_dir(self.trace_id)
        os.makedirs(trace_dir, exist_ok=True)
        trace_log_path = os.path.join(trace_dir, "99_trace_log.json")
        
        existing_data = {}
        if os.path.exists(trace_log_path):
            try:
                with open(trace_log_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                existing_data = {}
        
        # Initialize steps array if it doesn't exist
        if "steps" not in existing_data:
            existing_data["steps"] = []
        
        # Add the new step
        existing_data["steps"].append(step_entry)
        
        # Save updated data
        with open(trace_log_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
    
    def log_retrieval(self, retrieved_chunks):
        """Log retrieval results with simplified interface"""
        if not self.trace_id:
            raise ValueError("TraceHandler must be initialized with trace_id to use log_retrieval")
        
        # Create retrieval entry
        retrieval_entry = {"timestamp": datetime.now().isoformat(), "step": "retrieval", "data": retrieved_chunks}
        
        # Load existing trace data
        trace_dir = self.get_trace_dir(self.trace_id)
        os.makedirs(trace_dir, exist_ok=True)
        trace_log_path = os.path.join(trace_dir, "99_trace_log.json")
        
        existing_data = {}
        if os.path.exists(trace_log_path):
            try:
                with open(trace_log_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                existing_data = {}
        
        # Initialize steps array if it doesn't exist
        if "steps" not in existing_data:
            existing_data["steps"] = []
        
        # Add the retrieval step
        existing_data["steps"].append(retrieval_entry)
        
        # Save updated data
        with open(trace_log_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
    
    def log_error(self, error_message: str):
        """Log an error message"""
        if not self.trace_id:
            raise ValueError("TraceHandler must be initialized with trace_id to use log_error")
        
        # Create error entry
        error_entry = {"timestamp": datetime.now().isoformat(), "step": "error", "data": {"message": error_message}}
        
        # Load existing trace data
        trace_dir = self.get_trace_dir(self.trace_id)
        os.makedirs(trace_dir, exist_ok=True)
        trace_log_path = os.path.join(trace_dir, "99_trace_log.json")
        
        existing_data = {}
        if os.path.exists(trace_log_path):
            try:
                with open(trace_log_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                existing_data = {}
        
        # Initialize steps array if it doesn't exist
        if "steps" not in existing_data:
            existing_data["steps"] = []
        
        # Add the error step
        existing_data["steps"].append(error_entry)
        
        # Save updated data
        with open(trace_log_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
    
    def get_trace_summary(self, trace_id: str) -> Dict[str, Any]:
        """Get summary of trace files"""
        trace_dir = self.get_trace_dir(trace_id)
        
        if not os.path.exists(trace_dir):
            return {"error": "Trace directory not found"}
        
        files = os.listdir(trace_dir)
        summary = {
            "trace_id": trace_id,
            "trace_dir": trace_dir,
            "files": sorted(files),
            "created_at": datetime.fromtimestamp(os.path.getctime(trace_dir)).isoformat()
        }
        
        # Get file sizes
        file_sizes = {}
        for file in files:
            file_path = os.path.join(trace_dir, file)
            if os.path.isfile(file_path):
                file_sizes[file] = os.path.getsize(file_path)
        
        summary["file_sizes"] = file_sizes
        return summary
    
    def list_traces(self) -> List[Dict[str, Any]]:
        """List all available traces"""
        if not os.path.exists(self.base_traces_dir):
            return []
        
        traces = []
        for item in os.listdir(self.base_traces_dir):
            if item.startswith("trace_"):
                trace_path = os.path.join(self.base_traces_dir, item)
                if os.path.isdir(trace_path):
                    traces.append(self.get_trace_summary(item))
        
        return sorted(traces, key=lambda x: x["created_at"], reverse=True)
    
    def cleanup_old_traces(self, max_age_hours: int = 24):
        """Clean up traces older than specified hours"""
        if not os.path.exists(self.base_traces_dir):
            return
        
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        for item in os.listdir(self.base_traces_dir):
            if item.startswith("trace_"):
                trace_path = os.path.join(self.base_traces_dir, item)
                if os.path.isdir(trace_path):
                    creation_time = os.path.getctime(trace_path)
                    if current_time - creation_time > max_age_seconds:
                        import shutil
                        shutil.rmtree(trace_path)
                        print(f"Cleaned up old trace: {item}")
