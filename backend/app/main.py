from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import json
import asyncio
import time
from typing import Dict, Any
import uuid
from datetime import datetime

from .services.analysis_service import AnalysisService
from .services.llm_service import LLMService
from .services.rag_index import query_rag, get_collection_stats
from .services.rag_retrieve import retrieve_rules, retrieve_rules_batch, get_negation_chunks
from .models.analysis_models import AnalysisRequest, JobStatus
from .utils.file_handler import FileHandler
from .utils.trace_handler import TraceHandler

# Initialize FastAPI app
app = FastAPI(
    title="OCRD Extractor API",
    description="Modern OCRD document analysis with multiple LLM providers",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Wildcard origins cannot be used with credentials
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services with error handling
try:
    analysis_service = AnalysisService()
except Exception as e:
    print(f"Warning: Failed to initialize AnalysisService: {e}")
    analysis_service = None

try:
    llm_service = LLMService()
except Exception as e:
    print(f"Warning: Failed to initialize LLMService: {e}")
    llm_service = None

file_handler = FileHandler()
trace_handler = TraceHandler()

# In-memory job storage (in production, use Redis or database)
jobs: Dict[str, JobStatus] = {}

# Job persistence file
JOBS_FILE = "jobs_persistence.json"

def load_jobs():
    """Load jobs from persistence file"""
    global jobs
    try:
        if os.path.exists(JOBS_FILE):
            with open(JOBS_FILE, 'r') as f:
                jobs_data = json.load(f)
                for job_id, job_data in jobs_data.items():
                    jobs[job_id] = JobStatus(**job_data)
            print(f"Loaded {len(jobs)} jobs from persistence file")
    except Exception as e:
        print(f"Error loading jobs from persistence: {e}")

def save_jobs():
    """Save jobs to persistence file"""
    try:
        jobs_data = {job_id: job.dict() for job_id, job in jobs.items()}
        with open(JOBS_FILE, 'w') as f:
            json.dump(jobs_data, f, indent=2)
    except Exception as e:
        print(f"Error saving jobs to persistence: {e}")

# Load existing jobs on startup
load_jobs()

# Cleanup old jobs (older than 24 hours)
def cleanup_old_jobs():
    """Remove jobs older than 24 hours"""
    from datetime import datetime, timedelta
    current_time = datetime.now()
    jobs_to_remove = []
    
    for job_id, job in jobs.items():
        # Check if job is older than 24 hours
        if job.created_at:
            try:
                job_time = datetime.fromisoformat(job.created_at)
                job_age = current_time - job_time
                if job_age > timedelta(hours=24):
                    jobs_to_remove.append(job_id)
            except (ValueError, TypeError):
                # If created_at is invalid, remove the job
                jobs_to_remove.append(job_id)
    
    for job_id in jobs_to_remove:
        del jobs[job_id]
        print(f"Removed old job: {job_id}")
    
    if jobs_to_remove:
        save_jobs()

# Cleanup old jobs on startup
cleanup_old_jobs()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        self.active_connections[job_id] = websocket

    def disconnect(self, job_id: str):
        if job_id in self.active_connections:
            del self.active_connections[job_id]

    async def send_message(self, job_id: str, message: dict):
        if job_id in self.active_connections:
            try:
                await self.active_connections[job_id].send_text(json.dumps(message))
            except:
                self.disconnect(job_id)

manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main HTML page"""
    static_path = os.path.join(os.path.dirname(__file__), "..", "static", "index.html")
    with open(static_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Backward-compatible health endpoint under /api
@app.get("/api/health")
async def health_check_api():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/models")
async def get_available_models():
    """Get available LLM models"""
    if llm_service is None:
        return {
            "ollama_models": [],
            "openai_models": ["gpt-5", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
            "default_model": "gpt-5",
            "warning": "LLM service not initialized"
        }
    return {
        "ollama_models": llm_service.get_ollama_models() if llm_service else [],
        "openai_models": ["gpt-5", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
        "default_model": "gpt-5"
    }

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload and validate PDF file"""
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # Save file temporarily
        file_path = await file_handler.save_uploaded_file(file)
        
        return {
            "message": "File uploaded successfully",
            "filename": file.filename,
            "file_path": file_path,
            "size": os.path.getsize(file_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/api/analyze")
async def analyze_document(request: AnalysisRequest, enable_tracing: bool = True):
    """Start document analysis"""
    try:
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Generate trace ID if tracing is enabled
        trace_id = trace_handler.generate_trace_id() if enable_tracing else None
        
        # Initialize job status
        jobs[job_id] = JobStatus(
            job_id=job_id,
            status="queued",
            progress=0,
            message="Analysis queued",
            result=None,
            error=None,
            created_at=datetime.now().isoformat()
        )
        
        # Save to persistence
        save_jobs()
        
        # Start analysis in background
        asyncio.create_task(run_analysis(job_id, request, trace_id))
        
        response = {"job_id": job_id, "status": "queued"}
        if trace_id:
            response["trace_id"] = trace_id
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed to start: {str(e)}")

async def run_analysis(job_id: str, request: AnalysisRequest, trace_id: str = None):
    """Run analysis in background with progress updates"""
    try:
        print(f"Starting analysis for job {job_id}")
        
        # Check if job still exists
        if job_id not in jobs:
            print(f"Job {job_id} not found in jobs dictionary")
            return
            
        # Update status
        jobs[job_id].status = "processing"
        jobs[job_id].progress = 10
        jobs[job_id].message = "Extracting text from PDF"
        save_jobs()  # Save status update
        await manager.send_message(job_id, jobs[job_id].dict())
        
        # Extract text with or without tracing
        if trace_id:
            # Create trace directory
            await trace_handler.create_trace_directory(trace_id)
            
            # Save metadata
            meta_data = {
                "trace_id": trace_id,
                "job_id": job_id,
                "filename": os.path.basename(request.file_path),
                "file_path": request.file_path,
                "analysis_method": request.analysis_method.value,
                "llm_provider": request.llm_provider.value,
                "model": request.model,
                "fund_id": request.fund_id,
                "ocr_enabled": False,  # Currently not using OCR
                "extractor": "PyPDF2",
                "start_time": time.time(),
                "created_at": datetime.now().isoformat()
            }
            await trace_handler.save_meta(trace_id, meta_data)
            
            # Extract text with tracing
            extraction_result = await file_handler.extract_pdf_text_with_tracing(request.file_path, trace_id)
            text = extraction_result["clean_text"]
            
            # Update metadata with extraction info
            meta_data.update({
                "total_pages": extraction_result["total_pages"],
                "extraction_time": extraction_result["extraction_time"],
                "text_length": len(text),
                "chunks_count": len(extraction_result["chunks"])
            })
            await trace_handler.save_meta(trace_id, meta_data)
            
        else:
            # Regular text extraction
            text = await file_handler.extract_pdf_text(request.file_path)
        
        jobs[job_id].progress = 30
        jobs[job_id].message = "Text extracted, starting analysis"
        save_jobs()  # Save progress update
        await manager.send_message(job_id, jobs[job_id].dict())
        
        # Run analysis
        result = await analysis_service.analyze_document(
            text=text,
            analysis_method=request.analysis_method,
            llm_provider=request.llm_provider,
            model=request.model,
            fund_id=request.fund_id,
            trace_id=trace_id
        )
        
        jobs[job_id].progress = 90
        jobs[job_id].message = "Analysis complete, finalizing results"
        await manager.send_message(job_id, jobs[job_id].dict())
        
        # Complete job
        jobs[job_id].status = "completed"
        jobs[job_id].progress = 100
        jobs[job_id].message = "Analysis completed successfully"
        jobs[job_id].result = result
        
        # Log result summary for debugging
        allowed_count = result.get("allowed_instruments", 0)
        total_count = result.get("total_instruments", 0)
        notes_count = len(result.get("notes", []))
        print(f"[JOB {job_id}] Analysis complete: {allowed_count}/{total_count} allowed, {notes_count} notes")
        if notes_count > 0:
            print(f"[JOB {job_id}] First 3 notes: {result.get('notes', [])[:3]}")
        
        save_jobs()  # Save completion
        
        # Add trace_id to result if available
        if trace_id:
            jobs[job_id].result["trace_id"] = trace_id
        
        await manager.send_message(job_id, jobs[job_id].dict())
        
    except Exception as e:
        print(f"Analysis failed for job {job_id}: {str(e)}")
        print(f"Exception type: {type(e).__name__}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        # Only update job status if job still exists
        if job_id in jobs:
            jobs[job_id].status = "failed"
            jobs[job_id].error = str(e)
            jobs[job_id].message = f"Analysis failed: {str(e)}"
            save_jobs()  # Save error status
            await manager.send_message(job_id, jobs[job_id].dict())
        else:
            print(f"Job {job_id} not found when trying to update error status")

@app.get("/api/jobs")
async def list_jobs():
    """List all jobs (for debugging)"""
    return {
        "total_jobs": len(jobs),
        "jobs": {job_id: job.dict() for job_id, job in jobs.items()}
    }

@app.get("/api/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    """Get job status"""
    # Reduced logging to prevent log spam
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    job_status = jobs[job_id].dict()
    # Only log if status changed or if it's an error state
    status = job_status.get("status", "unknown")
    if status in ["completed", "failed"]:
        # Log once for completed/failed jobs, but don't spam
        pass
    return job_status

@app.get("/api/jobs/{job_id}/results")
async def get_job_results(job_id: str):
    """Get job results"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not completed yet")
    
    return job.result

@app.get("/api/jobs/{job_id}/export/excel")
async def export_excel(job_id: str):
    """Export results to Excel"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not completed yet")
    
    excel_path = await file_handler.create_excel_export(job.result)
    return FileResponse(
        path=excel_path,
        filename=f"ocrd_results_{job_id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.get("/api/jobs/{job_id}/export/mapping")
async def export_mapping_excel(job_id: str):
    """Export Excel mapping table with filled ticks"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not completed yet")
    
    # Check if Excel mapping path exists in result
    if analysis_service and analysis_service.excel_mapping:
        excel_path = os.path.join(file_handler.export_dir, f"mapping_results_{job_id}.xlsx")
        analysis_service.excel_mapping.export_to_excel(excel_path)
        return FileResponse(
            path=excel_path,
            filename=f"instrument_mapping_{job_id}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        raise HTTPException(status_code=404, detail="Excel mapping not available for this job")

@app.get("/api/jobs/{job_id}/export/json")
async def export_json(job_id: str):
    """Export results to JSON"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not completed yet")
    
    return job.result

@app.websocket("/ws/jobs/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket, job_id)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(job_id)

# Trace management endpoints
@app.get("/api/traces")
async def list_traces():
    """List all available traces"""
    try:
        # Debug: Check if traces directory exists
        traces_dir = trace_handler.base_traces_dir
        if not os.path.exists(traces_dir):
            return {"traces": [], "count": 0, "debug": f"Traces directory does not exist: {traces_dir}"}
        
        traces = trace_handler.list_traces()
        return {"traces": traces, "count": len(traces), "debug": f"Traces directory: {traces_dir}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list traces: {str(e)}")

@app.get("/api/traces/{trace_id}")
async def get_trace(trace_id: str):
    """Get trace details"""
    try:
        summary = trace_handler.get_trace_summary(trace_id)
        if "error" in summary:
            raise HTTPException(status_code=404, detail=summary["error"])
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trace: {str(e)}")

@app.get("/api/traces/{trace_id}/files/{filename}")
async def get_trace_file(trace_id: str, filename: str):
    """Get specific trace file content"""
    try:
        trace_dir = trace_handler.get_trace_dir(trace_id)
        file_path = os.path.join(trace_dir, filename)
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Return appropriate content type based on file extension
        if filename.endswith('.json'):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
            return content
        elif filename.endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {"content": content}
        elif filename.endswith('.jsonl'):
            lines = []
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    lines.append(json.loads(line.strip()))
            return {"lines": lines}
        else:
            # Return as text file
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {"content": content}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trace file: {str(e)}")

@app.delete("/api/traces/{trace_id}")
async def delete_trace(trace_id: str):
    """Delete a trace"""
    try:
        trace_dir = trace_handler.get_trace_dir(trace_id)
        if not os.path.exists(trace_dir):
            raise HTTPException(status_code=404, detail="Trace not found")
        
        import shutil
        shutil.rmtree(trace_dir)
        return {"message": f"Trace {trace_id} deleted successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete trace: {str(e)}")

@app.post("/api/traces/cleanup")
async def cleanup_traces(max_age_hours: int = 24):
    """Clean up old traces"""
    try:
        trace_handler.cleanup_old_traces(max_age_hours)
        return {"message": f"Cleaned up traces older than {max_age_hours} hours"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup traces: {str(e)}")

@app.post("/api/traces/test")
async def create_test_trace():
    """Create a test trace for debugging"""
    try:
        trace_id = trace_handler.generate_trace_id()
        await trace_handler.create_trace_directory(trace_id)
        
        # Create test metadata
        test_meta = {
            "trace_id": trace_id,
            "test": True,
            "created_at": datetime.now().isoformat(),
            "message": "This is a test trace"
        }
        await trace_handler.save_meta(trace_id, test_meta)
        
        return {"message": f"Test trace created: {trace_id}", "trace_id": trace_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create test trace: {str(e)}")

# RAG Query Endpoints
@app.post("/api/rag/query")
async def query_rag_index(query: str, n_results: int = 5, doc_id: str = None):
    """Query the RAG index for relevant document chunks"""
    try:
        vectordb_dir = "/tmp/chroma"
        results = query_rag(
            vectordb_dir=vectordb_dir,
            query=query,
            n_results=n_results,
            doc_id=doc_id
        )
        
        if not results["success"]:
            raise HTTPException(status_code=500, detail=results["error"])
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(e)}")

@app.get("/api/rag/stats")
async def get_rag_stats():
    """Get statistics about the RAG index"""
    try:
        vectordb_dir = "/tmp/chroma"
        stats = get_collection_stats(vectordb_dir)
        
        if not stats["success"]:
            raise HTTPException(status_code=500, detail=stats["error"])
        
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get RAG stats: {str(e)}")

# RAG Retrieval Endpoints for Decision Items
@app.post("/api/rag/retrieve")
async def retrieve_decision_rules(query: str, doc_id: str, k: int = 5):
    """Retrieve rules for a specific decision item (sector, country, etc.)"""
    try:
        vectordb_dir = "/tmp/chroma"
        results = retrieve_rules(query, doc_id, k, vectordb_dir)
        
        return {
            "success": True,
            "query": query,
            "doc_id": doc_id,
            "k": k,
            "results": results,
            "count": len(results)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG retrieval failed: {str(e)}")

@app.post("/api/rag/retrieve/batch")
async def retrieve_decision_rules_batch(queries: list, doc_id: str, k: int = 5):
    """Retrieve rules for multiple decision items in batch"""
    try:
        vectordb_dir = "/tmp/chroma"
        results = retrieve_rules_batch(queries, doc_id, k, vectordb_dir)
        
        return {
            "success": True,
            "queries": queries,
            "doc_id": doc_id,
            "k": k,
            "results": results,
            "total_queries": len(queries)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch RAG retrieval failed: {str(e)}")

@app.post("/api/rag/negations")
async def retrieve_negation_chunks(query: str, doc_id: str, k: int = 5):
    """Retrieve only negation-bearing chunks for a decision item"""
    try:
        vectordb_dir = "/tmp/chroma"
        results = get_negation_chunks(query, doc_id, k, vectordb_dir)
        
        return {
            "success": True,
            "query": query,
            "doc_id": doc_id,
            "k": k,
            "negation_chunks": results,
            "count": len(results)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Negation retrieval failed: {str(e)}")

# Mount static files
import os
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
