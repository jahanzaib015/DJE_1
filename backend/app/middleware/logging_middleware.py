"""
FastAPI middleware for logging all HTTP requests and responses.
"""
import time
import json
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message
from ..utils.logger import get_request_logger

logger = get_request_logger()

class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests and responses"""
    
    async def dispatch(self, request: Request, call_next):
        # Generate request ID
        request_id = request.headers.get("X-Request-ID", f"req_{int(time.time() * 1000)}")
        
        # Start timer
        start_time = time.time()
        
        # Log request
        client_host = request.client.host if request.client else "unknown"
        method = request.method
        url = str(request.url)
        path = request.url.path
        query_params = dict(request.query_params)
        
        # Get request body (if any)
        request_body = None
        if method in ["POST", "PUT", "PATCH"]:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    # Store body for later use
                    async def receive():
                        return {"type": "http.request", "body": body_bytes}
                    request._receive = receive
                    
                    # Try to parse as JSON
                    try:
                        request_body = json.loads(body_bytes.decode('utf-8'))
                    except:
                        # If not JSON, log as string (truncated)
                        body_str = body_bytes.decode('utf-8', errors='ignore')
                        if len(body_str) > 1000:
                            request_body = body_str[:1000] + "... [truncated]"
                        else:
                            request_body = body_str
            except Exception as e:
                logger.debug(f"Could not read request body: {e}")
        
        # Log incoming request
        log_data = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "query_params": query_params,
            "client_host": client_host,
            "headers": dict(request.headers),
        }
        
        if request_body:
            # Mask sensitive data
            if isinstance(request_body, dict):
                masked_body = self._mask_sensitive_data(request_body)
                log_data["body"] = masked_body
            else:
                log_data["body_preview"] = str(request_body)[:500]
        
        logger.info(f"📥 INCOMING REQUEST [{request_id}] {method} {path}")
        logger.debug(f"Request details: {json.dumps(log_data, indent=2, default=str)}")
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Log response
            status_code = response.status_code
            log_level = logging.INFO if status_code < 400 else logging.ERROR
            
            # Log response summary
            logger.log(
                log_level,
                f"📤 OUTGOING RESPONSE [{request_id}] {method} {path} | "
                f"Status: {status_code} | Duration: {duration:.3f}s"
            )
            
            # Log error details if status code indicates error
            if status_code >= 400:
                logger.error(f"❌ Error response [{request_id}]: Status {status_code} for {method} {path}")
            
            # Add custom headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration:.3f}"
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"❌ REQUEST FAILED [{request_id}] {method} {path} | "
                f"Error: {str(e)} | Duration: {duration:.3f}s",
                exc_info=True
            )
            raise
    
    def _mask_sensitive_data(self, data: dict) -> dict:
        """Mask sensitive fields in request/response data"""
        sensitive_keys = ['password', 'api_key', 'token', 'authorization', 'secret', 'access_token']
        masked = {}
        
        for key, value in data.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                masked[key] = "***MASKED***"
            elif isinstance(value, dict):
                masked[key] = self._mask_sensitive_data(value)
            elif isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                masked[key] = [self._mask_sensitive_data(item) for item in value]
            else:
                masked[key] = value
        
        return masked

