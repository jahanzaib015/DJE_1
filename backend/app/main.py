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

# Initialize services
analysis_service = AnalysisService()
llm_service = LLMService()
file_handler = FileHandler()
trace_handler = TraceHandler()

# In-memory job storage (in production, use Redis or database)
jobs: Dict[str, JobStatus] = {}

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
    return {
        "ollama_models": llm_service.get_ollama_models(),
        "openai_models": ["gpt-4", "gpt-3.5-turbo", "gpt-4-turbo"],
        "default_model": "gpt-4"
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
            error=None
        )
        
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
        # Update status
        jobs[job_id].status = "processing"
        jobs[job_id].progress = 10
        jobs[job_id].message = "Extracting text from PDF"
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
        
        # Add trace_id to result if available
        if trace_id:
            jobs[job_id].result["trace_id"] = trace_id
        
        await manager.send_message(job_id, jobs[job_id].dict())
        
    except Exception as e:
        jobs[job_id].status = "failed"
        jobs[job_id].error = str(e)
        jobs[job_id].message = f"Analysis failed: {str(e)}"
        await manager.send_message(job_id, jobs[job_id].dict())

@app.get("/api/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    """Get job status"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return jobs[job_id].dict()

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

# Mount static files
import os
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
