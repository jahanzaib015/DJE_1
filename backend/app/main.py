from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import json
import asyncio
import time
from typing import Dict, Any, List
import uuid
from datetime import datetime

from .models.catalog_models import (
    ClassificationRequest,
    ClassificationResult,
    InvestmentOffering,
    CatalogItem
)
from .models.analysis_models import AnalysisRequest, JobStatus
from .utils.file_handler import FileHandler
from .utils.trace_handler import TraceHandler
from .utils.logger import setup_logger
from .middleware.logging_middleware import LoggingMiddleware
from .models.analysis_models import AnalysisMethod, LLMProvider

# Set up logging
logger = setup_logger(__name__)

print("[boot] app.main imported", flush=True)

# Ensure PORT is available for Render
import os
PORT = os.getenv("PORT", "8000")
print(f"[boot] PORT environment variable: {PORT}", flush=True)

# --- Lazy imports removed - services loaded on demand ---

def get_enum_value(value):
    """Safely get enum value, handling both enum objects and strings"""
    if hasattr(value, 'value'):
        return value.value
    return str(value)

# Initialize FastAPI app
app = FastAPI(
    title="OCRD Extractor API",
    description="Modern OCRD document analysis with multiple LLM providers",
    version="1.0.0"
)

# Add exception handler for validation errors to see what's wrong
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Custom handler to log validation errors in detail"""
    errors = exc.errors()
    error_details = []
    for error in errors:
        error_details.append({
            "field": ".".join(str(x) for x in error.get("loc", [])),
            "message": error.get("msg"),
            "type": error.get("type"),
            "input": error.get("input")
        })
    
    logger.error(f"Validation error on {request.url.path}: {error_details}")
    
    # Try to log request body
    try:
        body = await request.body()
        if body:
            logger.debug(f"Request body: {body.decode('utf-8', errors='ignore')[:500]}")
    except:
        pass
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": error_details,
            "message": "Validation error - check the 'detail' field for specific field errors"
        }
    )

# Logging middleware (should be added before other middleware for full request/response logging)
app.add_middleware(LoggingMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Wildcard origins cannot be used with credentials
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# LAZY IMPORTS / LAZY SERVICES
# ----------------------------
analysis_service = None
llm_service = None
catalog_service = None
classification_service = None

def get_analysis_service():
    global analysis_service
    if analysis_service is None:
        from .services.analysis_service import AnalysisService
        analysis_service = AnalysisService(excel_mapping_path=None)
    return analysis_service

def get_llm_service():
    global llm_service
    if llm_service is None:
        from .services.llm_service import LLMService
        llm_service = LLMService()
    return llm_service

def get_catalog_service():
    global catalog_service
    if catalog_service is None:
        from .services.catalog_service import CatalogService
        catalog_service = CatalogService()
    return catalog_service

def get_classification_service():
    global classification_service
    if classification_service is None:
        cs = get_catalog_service()
        from .services.classification_service import ClassificationService
        classification_service = ClassificationService(catalog_service=cs)
    return classification_service

@app.on_event("startup")
async def startup_cleanup():
    """Cleanup old jobs on startup (moved from import-time to prevent blocking)"""
    await asyncio.to_thread(cleanup_old_jobs)
    logger.info("Startup cleanup complete - API ready (services will load on demand)")

# Services are now loaded lazily on first use via get_*_service() functions

# Lazy initialization - create handlers when first needed
file_handler = None
trace_handler = None

def get_file_handler():
    """Get file handler (lazy initialization)"""
    global file_handler
    if file_handler is None:
        file_handler = FileHandler()
    return file_handler

def get_trace_handler():
    """Get trace handler (lazy initialization)"""
    global trace_handler
    if trace_handler is None:
        trace_handler = TraceHandler()
    return trace_handler

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
            logger.debug(f"Loaded {len(jobs)} jobs from persistence file")
        else:
            logger.debug("No existing jobs file found, starting fresh")
    except Exception as e:
        logger.error(f"Error loading jobs from persistence: {e}")

def save_jobs():
    """Save jobs to persistence file"""
    try:
        jobs_data = {job_id: job.dict() for job_id, job in jobs.items()}
        with open(JOBS_FILE, 'w') as f:
            json.dump(jobs_data, f, indent=2)
        logger.debug(f"Saved {len(jobs)} jobs to persistence file")
    except Exception as e:
        logger.error(f"Error saving jobs to persistence: {e}")

# Load existing jobs in background (don't block startup)
@app.on_event("startup")
async def load_jobs_background():
    """Load jobs in background without blocking"""
    await asyncio.to_thread(load_jobs)

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
        logger.debug(f"Removed old job: {job_id}")
    
    if jobs_to_remove:
        save_jobs()
        logger.debug(f"Cleaned up {len(jobs_to_remove)} old jobs")

# Cleanup old jobs moved to startup event (import-time work can delay binding)

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
    """Health check endpoint - fast response for Render health checks"""
    # This endpoint must respond quickly for Render port detection
    try:
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        # Even if there's an error, return something so port is detected
        return {"status": "healthy", "error": str(e)}

@app.get("/health/live")
async def liveness_check():
    """Liveness check - minimal check that app is running"""
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness_check():
    """Readiness check - verify services are ready"""
    from fastapi import Response
    # Services load on demand, so we're always ready
    ready = {
        "status": "ready",
        "services": {
            "analysis_service": True,  # Will load on first use
            "llm_service": True  # Will load on first use
        }
    }
    return Response(content=json.dumps(ready), status_code=200, media_type="application/json")

# Backward-compatible health endpoint under /api
@app.get("/api/health")
async def health_check_api():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/models")
async def get_available_models():
    """Get available LLM models"""
    svc = get_llm_service()
    return {
        "ollama_models": svc.get_ollama_models(),
        "openai_models": svc.get_openai_models(),
        "default_model": "gpt-5.1"
    }

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload and validate PDF file"""
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # Save file temporarily
        file_path = await get_file_handler().save_uploaded_file(file)
        
        return {
            "message": "File uploaded successfully",
            "filename": file.filename,
            "file_path": file_path,
            "size": os.path.getsize(file_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/api/analyze/test")
async def test_analyze_endpoint(request: AnalysisRequest):
    """Test endpoint to verify request validation works"""
    return {
        "message": "Request validated successfully",
        "received": {
            "file_path": request.file_path,
            "analysis_method": str(request.analysis_method),
            "llm_provider": str(request.llm_provider),
            "model": request.model,
            "fund_id": request.fund_id
        }
    }

@app.post("/api/analyze")
async def analyze_document(request: AnalysisRequest, enable_tracing: bool = True):
    """Start document analysis"""
    try:
        # Log the received request for debugging
        logger.debug(f"Received analysis request: file_path={request.file_path}, method={request.analysis_method}, provider={request.llm_provider}, model={request.model}")
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Generate trace ID if tracing is enabled
        trace_id = get_trace_handler().generate_trace_id() if enable_tracing else None
        
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
        
        # Save to persistence in background (don't block response)
        asyncio.create_task(asyncio.to_thread(save_jobs))
        
        # Start analysis in background
        asyncio.create_task(run_analysis(job_id, request, trace_id))
        
        response = {"job_id": job_id, "status": "queued"}
        if trace_id:
            response["trace_id"] = trace_id
        
        logger.debug(f"Analysis job {job_id} queued")
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed to start: {str(e)}")

async def run_analysis(job_id: str, request: AnalysisRequest, trace_id: str = None):
    """Run analysis in background with progress updates"""
    # Maximum time for entire analysis (15 minutes)
    MAX_ANALYSIS_TIME = 900.0
    
    try:
        # Wrap entire analysis in timeout to prevent hanging
        await asyncio.wait_for(
            _run_analysis_internal(job_id, request, trace_id),
            timeout=MAX_ANALYSIS_TIME
        )
    except asyncio.TimeoutError:
        logger.error(f"Analysis job {job_id} timed out after {MAX_ANALYSIS_TIME}s")
        if job_id in jobs:
            jobs[job_id].status = "failed"
            jobs[job_id].progress = 0
            jobs[job_id].error = f"Analysis timed out after {MAX_ANALYSIS_TIME} seconds. Document may be too large or API is slow."
            save_jobs()
            await manager.send_message(job_id, jobs[job_id].dict())
    except Exception as e:
        logger.error(f"Analysis job {job_id} failed: {e}")
        if job_id in jobs:
            jobs[job_id].status = "failed"
            jobs[job_id].progress = 0
            jobs[job_id].error = str(e)
            save_jobs()
            await manager.send_message(job_id, jobs[job_id].dict())

async def _run_analysis_internal(job_id: str, request: AnalysisRequest, trace_id: str = None):
    """Internal analysis function with progress updates"""
    try:
        logger.info(f"Starting analysis job {job_id} | Method: {get_enum_value(request.analysis_method)} | Provider: {get_enum_value(request.llm_provider)}")
        
        # Check if job still exists
        if job_id not in jobs:
            logger.warning(f"Job {job_id} not found in jobs dictionary")
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
            await get_trace_handler().create_trace_directory(trace_id)
            
            # Save metadata
            meta_data = {
                "trace_id": trace_id,
                "job_id": job_id,
                "filename": os.path.basename(request.file_path),
                "file_path": request.file_path,
                "analysis_method": get_enum_value(request.analysis_method),
                "llm_provider": get_enum_value(request.llm_provider),
                "model": request.model,
                "fund_id": request.fund_id,
                "ocr_enabled": False,  # Currently not using OCR
                "extractor": "PyPDF2",
                "start_time": time.time(),
                "created_at": datetime.now().isoformat()
            }
            await get_trace_handler().save_meta(trace_id, meta_data)
            
            # Extract text with tracing
            extraction_result = await get_file_handler().extract_pdf_text_with_tracing(request.file_path, trace_id)
            text = extraction_result["clean_text"]
            is_image_only = extraction_result.get("is_image_only", False)
            
            # Update metadata with extraction info
            meta_data.update({
                "total_pages": extraction_result["total_pages"],
                "extraction_time": extraction_result["extraction_time"],
                "text_length": len(text),
                "chunks_count": len(extraction_result.get("chunks", [])),
                "is_image_only": is_image_only
            })
            await get_trace_handler().save_meta(trace_id, meta_data)
            
        else:
            # Regular text extraction
            text = await get_file_handler().extract_pdf_text(request.file_path)
            # Check if image-only for non-traced extraction too
            is_image_only = get_file_handler().is_image_only_pdf(request.file_path)
        
        jobs[job_id].progress = 30
        if is_image_only:
            jobs[job_id].message = "Image-only PDF detected, using vision analysis"
        else:
            jobs[job_id].message = "Text extracted, converting to markdown"
        save_jobs()  # Save progress update
        await manager.send_message(job_id, jobs[job_id].dict())
        
        # Convert text to markdown and save it
        markdown_path = None
        markdown_text = None
        if not is_image_only:
            try:
                # Generate filename from original PDF or job_id
                original_filename = os.path.basename(request.file_path)
                filename_base = os.path.splitext(original_filename)[0] if original_filename else f"document_{job_id}"
                
                # Save text as markdown
                markdown_path = await get_file_handler().save_text_as_markdown(
                    text=text,
                    job_id=job_id,
                    filename=filename_base
                )
                
                # Read the markdown file
                markdown_text = await get_file_handler().read_markdown_file(markdown_path)
                
                jobs[job_id].progress = 40
                jobs[job_id].message = "Markdown file created, starting analysis"
                save_jobs()
                await manager.send_message(job_id, jobs[job_id].dict())
                
                logger.info(f"✅ Markdown conversion complete: {markdown_path}")
            except Exception as e:
                logger.error(f"❌ Markdown conversion failed: {e}", exc_info=True)
                # Fallback to original text if markdown conversion fails
                markdown_text = text
                logger.warning("⚠️ Falling back to original text for analysis")
        
        # Run analysis - use vision pipeline for image-only PDFs
        svc = get_analysis_service()
        if is_image_only:
            logger.info(f"📸 Using vision pipeline for image-only PDF: {request.file_path}")
            result = await svc.analyze_document_vision(
                pdf_path=request.file_path,
                analysis_method=request.analysis_method,
                llm_provider=request.llm_provider,
                model=request.model,
                fund_id=request.fund_id,
                trace_id=trace_id
            )
        else:
            # Use markdown text if available, otherwise fallback to original text
            text_for_analysis = markdown_text if markdown_text else text
            logger.info(f"📄 Using {'markdown' if markdown_text else 'original text'} for analysis")
            
            result = await svc.analyze_document(
                text=text_for_analysis,
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
        logger.info(f"Analysis complete [{job_id}]: {allowed_count}/{total_count} allowed instruments, {notes_count} notes")
        if notes_count > 0:
            logger.debug(f"[JOB {job_id}] First 3 notes: {result.get('notes', [])[:3]}")
        
        # Add trace_id to result if available
        if trace_id:
            jobs[job_id].result["trace_id"] = trace_id
        
        save_jobs()  # Save completion
        await manager.send_message(job_id, jobs[job_id].dict())
        
    except Exception as e:
        logger.error(f"Analysis failed for job {job_id}: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        
        # Only update job status if job still exists
        if job_id in jobs:
            jobs[job_id].status = "failed"
            jobs[job_id].error = str(e)
            jobs[job_id].message = f"Analysis failed: {str(e)}"
            save_jobs()  # Save error status
            await manager.send_message(job_id, jobs[job_id].dict())
            logger.debug(f"Updated job {job_id} status to failed")
        else:
            logger.warning(f"Job {job_id} not found when trying to update error status")

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
    """Export results to Excel - includes ALL 137 mapping entries"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not completed yet")
    
    # If Excel mapping is available, export the full mapping table (137 entries)
    svc = get_analysis_service()
    if svc and svc.excel_mapping and len(svc.excel_mapping.get_all_entries()) > 0:
        excel_path = os.path.join(get_file_handler().export_dir, f"full_mapping_results_{job_id}.xlsx")
        svc.excel_mapping.export_to_excel(excel_path)
        return FileResponse(
            path=excel_path,
            filename=f"instrument_mapping_full_{job_id}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        # Fallback to OCRD export if mapping not available
        excel_path = await get_file_handler().create_excel_export(job.result)
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
    svc = get_analysis_service()
    if svc and svc.excel_mapping:
        excel_path = os.path.join(get_file_handler().export_dir, f"mapping_results_{job_id}.xlsx")
        svc.excel_mapping.export_to_excel(excel_path)
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
        traces_dir = get_trace_handler().base_traces_dir
        if not os.path.exists(traces_dir):
            return {"traces": [], "count": 0, "debug": f"Traces directory does not exist: {traces_dir}"}
        
        traces = get_trace_handler().list_traces()
        return {"traces": traces, "count": len(traces), "debug": f"Traces directory: {traces_dir}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list traces: {str(e)}")

@app.get("/api/traces/{trace_id}")
async def get_trace(trace_id: str):
    """Get trace details"""
    try:
        summary = get_trace_handler().get_trace_summary(trace_id)
        if "error" in summary:
            raise HTTPException(status_code=404, detail=summary["error"])
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trace: {str(e)}")

@app.get("/api/traces/{trace_id}/files/{filename}")
async def get_trace_file(trace_id: str, filename: str):
    """Get specific trace file content"""
    try:
        trace_dir = get_trace_handler().get_trace_dir(trace_id)
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
        trace_dir = get_trace_handler().get_trace_dir(trace_id)
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
        get_trace_handler().cleanup_old_traces(max_age_hours)
        return {"message": f"Cleaned up traces older than {max_age_hours} hours"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup traces: {str(e)}")

@app.post("/api/traces/test")
async def create_test_trace():
    """Create a test trace for debugging"""
    try:
        trace_id = get_trace_handler().generate_trace_id()
        await get_trace_handler().create_trace_directory(trace_id)
        
        # Create test metadata
        test_meta = {
            "trace_id": trace_id,
            "test": True,
            "created_at": datetime.now().isoformat(),
            "message": "This is a test trace"
        }
        await get_trace_handler().save_meta(trace_id, test_meta)
        
        return {"message": f"Test trace created: {trace_id}", "trace_id": trace_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create test trace: {str(e)}")

# RAG Query Endpoints
@app.post("/api/rag/query")
async def query_rag_index(query: str, n_results: int = 5, doc_id: str = None):
    """Query the RAG index for relevant document chunks"""
    try:
        from .services.rag_index import query_rag
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
        from .services.rag_index import get_collection_stats
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
        from .services.rag_retrieve import retrieve_rules
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
        from .services.rag_retrieve import retrieve_rules_batch
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
        from .services.rag_retrieve import get_negation_chunks
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

@app.get("/debug/rag")
async def debug_rag(fund_id: str = "5800", k: int = 5):
    """Quick debug endpoint to view chunks without running full analysis"""
    try:
        from .services.rag_retrieve import retrieve_rules
        # Use fund_id as doc_id and a generic query for investment rules
        query = "investment rules allowed restricted sectors countries instruments"
        doc_id = fund_id
        vectordb_dir = "/tmp/chroma"
        
        chunks = retrieve_rules(query, doc_id, k, vectordb_dir)
        
        return {
            "fund_id": fund_id,
            "count": len(chunks),
            "previews": [c.get("text", str(c))[:300] for c in chunks],
            "chunks": [
                {
                    "id": c.get("id", None),
                    "score": c.get("distance", None),  # distance is the relevance score (lower is better)
                    "text_preview": c.get("text", str(c))[:300],
                    "meta": c.get("meta", {})
                }
                for c in chunks
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debug RAG retrieval failed: {str(e)}")

# ============================================================================
# Investment Classification & Catalog Management Endpoints
# ============================================================================

@app.post("/api/classify", response_model=ClassificationResult)
async def classify_document(request: ClassificationRequest):
    """Classify a document against the investment catalog"""
    try:
        svc = get_classification_service()
        result = svc.classify_document(request)
        return result
        
    except Exception as e:
        logger.error(f"Classification failed: {e}")
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")


@app.get("/api/catalog", response_model=List[CatalogItem])
async def get_catalog(active_only: bool = True):
    """Get all catalog offerings"""
    try:
        svc = get_catalog_service()
        items = svc.get_all_offerings(active_only=active_only)
        return items
        
    except Exception as e:
        logger.error(f"Failed to get catalog: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get catalog: {str(e)}")


@app.get("/api/catalog/{offering_id}", response_model=CatalogItem)
async def get_offering(offering_id: str):
    """Get a specific catalog offering by ID"""
    try:
        svc = get_catalog_service()
        item = svc.get_offering_by_id(offering_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"Offering '{offering_id}' not found")
        
        return item
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get offering: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get offering: {str(e)}")


@app.post("/api/catalog", response_model=CatalogItem)
async def create_offering(offering: InvestmentOffering):
    """Create a new catalog offering"""
    try:
        svc = get_catalog_service()
        success = svc.add_offering(offering)
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to create offering. ID '{offering.id}' may already exist."
            )
        
        created = svc.get_offering_by_id(offering.id)
        if not created:
            raise HTTPException(status_code=500, detail="Failed to retrieve created offering")
        
        # Rebuild classification index
        cls_svc = get_classification_service()
        if cls_svc:
            cls_svc._rebuild_index()
        
        return created
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create offering: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create offering: {str(e)}")


@app.put("/api/catalog/{offering_id}", response_model=CatalogItem)
async def update_offering(offering_id: str, offering: InvestmentOffering):
    """Update an existing catalog offering"""
    try:
        svc = get_catalog_service()
        
        # Ensure ID matches
        offering.id = offering_id
        
        success = svc.update_offering(offering_id, offering)
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Offering '{offering_id}' not found"
            )
        
        updated = svc.get_offering_by_id(offering_id)
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to retrieve updated offering")
        
        # Rebuild classification index
        cls_svc = get_classification_service()
        if cls_svc:
            cls_svc._rebuild_index()
        
        return updated
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update offering: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update offering: {str(e)}")


@app.delete("/api/catalog/{offering_id}")
async def delete_offering(offering_id: str):
    """Delete a catalog offering"""
    try:
        svc = get_catalog_service()
        success = svc.delete_offering(offering_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Offering '{offering_id}' not found"
            )
        
        # Rebuild classification index
        cls_svc = get_classification_service()
        if cls_svc:
            cls_svc._rebuild_index()
        
        return {"success": True, "message": f"Offering '{offering_id}' deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete offering: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete offering: {str(e)}")


# Mount static files
import os
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

if __name__ == "__main__":
    # For local development
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port, reload=True)
