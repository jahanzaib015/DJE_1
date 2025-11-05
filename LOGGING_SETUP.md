# Comprehensive Logging Setup

This document describes the comprehensive logging system implemented across the entire stack.

## Overview

The logging system provides:
- **Structured logging** across Frontend, Node.js backend, and Python backend
- **Request/Response tracing** with unique request IDs
- **File-based logging** for Python backend with rotation
- **Console logging** for all components with different levels
- **Sensitive data masking** to protect API keys and passwords

## Architecture

### 1. Python Backend (FastAPI)

**Location:** `backend/app/utils/logger.py`

**Features:**
- File-based logging with rotation (10MB files, 5 backups)
- Separate log files:
  - `logs/app.log` - All application logs
  - `logs/error.log` - Only errors
  - `logs/requests.log` - HTTP request/response logs
- Log levels: DEBUG, INFO, WARNING, ERROR
- Console output for INFO and above

**Usage:**
```python
from ..utils.logger import setup_logger

logger = setup_logger(__name__)
logger.info("Message")
logger.error("Error message", exc_info=True)
```

**Request/Response Logging:**
- Middleware automatically logs all HTTP requests/responses
- Includes request ID, method, path, duration, status code
- Request/response bodies are logged (with sensitive data masked)

**Location:** `backend/app/middleware/logging_middleware.py`

### 2. Node.js Backend (Express)

**Features:**
- Request/response logging with unique request IDs
- Morgan HTTP logger for error responses
- Detailed logging for all API endpoints
- Request ID propagation to Python backend

**Usage:**
- All requests automatically get a request ID
- Logs include: method, path, status, duration
- Request/response data is logged with error details

### 3. Frontend (React/TypeScript)

**Location:** `frontend/src/utils/logger.ts`

**Features:**
- Structured logging utility
- Request/response logging for all API calls
- Configurable log levels (debug, info, warn, error)
- Sensitive data masking
- Request ID generation and tracking

**Usage:**
```typescript
import { logger } from '../utils/logger';

logger.info('Message', { context });
logger.error('Error', { error: error.message });
```

**API Request Logging:**
- Automatically logs all outgoing requests
- Tracks request IDs across the stack
- Logs response status, duration, and data
- Error logging with full context

## Log Files

### Python Backend
- `backend/logs/app.log` - All application logs
- `backend/logs/error.log` - Only errors
- `backend/logs/requests.log` - HTTP requests/responses

### Log Rotation
- Max file size: 10MB
- Backup count: 5
- Automatic rotation when size limit reached

## Log Levels

### Python
- **DEBUG**: Detailed diagnostic information
- **INFO**: General informational messages
- **WARNING**: Warning messages
- **ERROR**: Error messages with stack traces

### Frontend/Node.js
- **debug**: Detailed debugging information
- **info**: General information
- **warn**: Warning messages
- **error**: Error messages

## Request ID Tracking

All requests are assigned a unique request ID that:
- Is generated in the frontend/Node.js backend
- Is passed through headers (`X-Request-ID`)
- Is logged at every step
- Allows tracing a request through the entire stack

## Sensitive Data Masking

The following fields are automatically masked in logs:
- `password`
- `api_key`
- `token`
- `authorization`
- `secret`
- `access_token`

## Configuration

### Frontend
Enable/disable logging in browser console:
```typescript
logger.enable();  // Enable logging
logger.disable(); // Disable logging
logger.setLevel('debug'); // Set log level
```

Or use localStorage:
```javascript
localStorage.setItem('enableLogging', 'true');
localStorage.setItem('logLevel', 'debug');
```

### Python Backend
Log levels are set in the logger setup. Default is INFO.

## Example Log Output

### Python Backend
```
2024-01-15 10:30:45 | INFO | Starting analysis for job abc123 | Method: llm_with_fallback | Provider: openai | Model: gpt-4o
2024-01-15 10:30:46 | DEBUG | [gpt-4o] Successfully parsed JSON response
2024-01-15 10:30:50 | INFO | ✅ [JOB abc123] Analysis complete: 45/137 allowed instruments, 3 notes
```

### Node.js Backend
```
📥 [req_1234567890] INCOMING POST /api/upload
✅ [req_1234567890] OUTGOING POST /api/upload | Status: 200 | Duration: 1250ms
```

### Frontend
```
📘 [2024-01-15T10:30:45.123Z] [INFO] 📤 OUTGOING REQUEST POST https://dje-1-3.onrender.com/api/upload [req_1234567890]
📥 [2024-01-15T10:30:46.456Z] [INFO] 📥 INCOMING RESPONSE POST https://dje-1-3.onrender.com/api/upload | Status: 200 | Duration: 1333ms [req_1234567890]
```

## Troubleshooting

### Enable Debug Logging
1. **Frontend**: Set log level to debug in browser console or localStorage
2. **Python**: Change log level in `logger.py` or use environment variable

### View Logs
1. **Python**: Check `backend/logs/` directory
2. **Node.js**: Check console output
3. **Frontend**: Check browser console (F12)

### Request Tracing
1. Find request ID in frontend logs
2. Search for that ID in all logs
3. Trace the request through the entire stack

## Best Practices

1. **Always include request IDs** when logging errors
2. **Use appropriate log levels** (don't log everything as ERROR)
3. **Include context** in log messages (job IDs, user IDs, etc.)
4. **Mask sensitive data** (already handled automatically)
5. **Use structured logging** (JSON objects) for better parsing

## Dependencies

- **Python**: Built-in `logging` module
- **Node.js**: `morgan` for HTTP logging
- **Frontend**: Custom logger utility (no external dependencies)

## Next Steps

To further enhance logging:
1. Add log aggregation (e.g., ELK stack, Splunk)
2. Add log monitoring and alerting
3. Add performance metrics
4. Add user activity tracking
5. Add audit logs for compliance

