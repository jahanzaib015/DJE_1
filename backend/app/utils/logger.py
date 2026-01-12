"""
Centralized logging configuration for the OCRD Extractor backend.
Provides structured logging with file and console handlers.
"""
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path

# Create logs directory if it doesn't exist
# Try multiple locations: project logs, /tmp/logs (for Render), or just use console
LOG_DIR = None
try:
    # Try project directory first
    LOG_DIR = Path(__file__).parent.parent.parent / "logs"
    LOG_DIR.mkdir(exist_ok=True, mode=0o755)
except (OSError, PermissionError):
    try:
        # Fallback to /tmp/logs (works on Render)
        LOG_DIR = Path("/tmp/logs")
        LOG_DIR.mkdir(exist_ok=True, mode=0o755)
    except (OSError, PermissionError):
        # If all else fails, we'll just use console logging
        LOG_DIR = None

# Log file paths (None if directory creation failed)
LOG_FILE = LOG_DIR / "app.log" if LOG_DIR else None
ERROR_LOG_FILE = LOG_DIR / "error.log" if LOG_DIR else None
REQUEST_LOG_FILE = LOG_DIR / "requests.log" if LOG_DIR else None

def _is_file_locked(file_path: Path, timeout: float = 0.1) -> bool:
    """
    Check if a file is locked by another process.
    Returns True if file appears to be locked, False otherwise.
    """
    if not file_path or not file_path.exists():
        return False
    
    try:
        # Simple check: try to open the file in append mode
        # If it's locked, this will fail on Windows
        if sys.platform == 'win32':
            try:
                # On Windows, try to open in exclusive mode
                with open(file_path, 'a', encoding='utf-8') as f:
                    pass
                return False  # File is not locked
            except (PermissionError, IOError, OSError):
                return True  # File is likely locked
        else:
            # On Unix, try to acquire a lock
            try:
                import fcntl
                with open(file_path, 'a', encoding='utf-8') as f:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        return False
                    except (IOError, OSError):
                        return True
            except ImportError:
                # fcntl not available, use simple check
                try:
                    with open(file_path, 'a', encoding='utf-8') as f:
                        pass
                    return False
                except (PermissionError, IOError, OSError):
                    return True
    except Exception:
        # If we can't check, assume it's not locked (safer to try)
        return False

class SuppressLogRotationErrors(logging.Filter):
    """Filter to suppress PermissionError messages from log rotation"""
    def filter(self, record):
        # Suppress PermissionError messages related to log rotation
        if record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type == PermissionError:
                error_msg = str(record.getMessage())
                if 'log' in error_msg.lower() and ('rotate' in error_msg.lower() or 'rollover' in error_msg.lower()):
                    return False  # Suppress this log record
        # Also suppress "Logging error" messages
        if "Logging error" in record.getMessage():
            return False
        return True

def _handle_logging_error(record):
    """Custom error handler to suppress log rotation errors"""
    # Suppress PermissionError from log rotation
    if record.exc_info and record.exc_info[0] == PermissionError:
        error_msg = str(record.getMessage())
        if 'log' in error_msg.lower() and ('rotate' in error_msg.lower() or 'rollover' in error_msg.lower()):
            return  # Suppress
    # Suppress "Logging error" messages
    if "Logging error" in record.getMessage():
        return  # Suppress

def setup_logger(name: str, log_file: Path = None, level: int = logging.INFO) -> logging.Logger:
    """
    Set up a logger with file and console handlers.
    
    Args:
        name: Logger name (usually __name__)
        log_file: Optional custom log file path
        level: Logging level (default: INFO)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers if logger already configured
    if logger.handlers:
        return logger
    
    # Add filter to suppress log rotation errors
    rotation_filter = SuppressLogRotationErrors()
    logger.addFilter(rotation_filter)
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Console handler (show info and above to display Excel mapping matches)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)  # Set to INFO to show Excel mapping matches
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (detailed logs) - only if file logging is available
    if log_file is None:
        log_file = LOG_FILE
    
    if log_file is not None:
        try:
            # Check if log file is locked before creating handler
            log_path = Path(log_file)
            if log_path.exists() and _is_file_locked(log_path):
                # File is locked - use console only for this logger
                print(f"Warning: Log file {log_file} is locked by another process. Using console logging only.", file=sys.stderr)
            else:
                # Create a custom handler that checks for locks before rotation
                class SafeRotatingFileHandler(RotatingFileHandler):
                    def doRollover(self):
                        """Override to add lock checking before rotation"""
                        try:
                            # Check if file is locked before attempting rotation
                            if self.baseFilename and _is_file_locked(Path(self.baseFilename)):
                                # File is locked - skip rotation to prevent crash
                                return
                            
                            # Check if rotation is needed
                            if self.stream is None:
                                return
                            
                            # Check file size
                            try:
                                if self.stream.tell() < self.maxBytes:
                                    return  # No rotation needed
                            except (OSError, AttributeError):
                                pass
                            
                            # Attempt rotation (call parent method)
                            super().doRollover()
                        except (OSError, PermissionError, IOError):
                            # Rotation failed silently - file is likely locked, just continue
                            # Don't print anything to avoid console spam
                            pass
                        except Exception:
                            # Unexpected error - suppress to avoid console spam
                            pass
                
                file_handler = SafeRotatingFileHandler(
                    log_file,
                    maxBytes=10 * 1024 * 1024,  # 10MB
                    backupCount=5,
                    encoding='utf-8',
                    delay=True  # Delay file opening until first log
                )
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(detailed_formatter)
                logger.addHandler(file_handler)
        except (OSError, PermissionError) as e:
            # If file logging fails, just use console (don't fail the app)
            print(f"Warning: Could not create file handler: {e}. Using console logging only.", file=sys.stderr)
    
    # Error file handler (only errors and above)
    if ERROR_LOG_FILE is not None:
        try:
            # Check if error log file is locked
            error_path = Path(ERROR_LOG_FILE)
            if error_path.exists() and _is_file_locked(error_path):
                # Skip error file handler if locked
                pass
            else:
                class SafeRotatingFileHandler(RotatingFileHandler):
                    def doRollover(self):
                        """Override to add lock checking before rotation"""
                        try:
                            if self.baseFilename and _is_file_locked(Path(self.baseFilename)):
                                return
                            if self.stream is None:
                                return
                            try:
                                if self.stream.tell() < self.maxBytes:
                                    return
                            except (OSError, AttributeError):
                                pass
                            super().doRollover()
                        except (OSError, PermissionError, IOError):
                            # Rotation failed silently - file is likely locked
                            pass
                        except Exception:
                            # Unexpected error - suppress
                            pass
                
                error_handler = SafeRotatingFileHandler(
                    ERROR_LOG_FILE,
                    maxBytes=10 * 1024 * 1024,  # 10MB
                    backupCount=5,
                    encoding='utf-8',
                    delay=True
                )
                error_handler.setLevel(logging.ERROR)
                error_handler.setFormatter(detailed_formatter)
                logger.addHandler(error_handler)
        except (OSError, PermissionError) as e:
            # If error file logging fails, continue without it
            pass
    
    return logger

def get_request_logger() -> logging.Logger:
    """Get a specialized logger for HTTP requests/responses"""
    logger = logging.getLogger("http_requests")
    logger.setLevel(logging.INFO)
    
    if logger.handlers:
        return logger
    
    # Request log formatter
    request_formatter = logging.Formatter(
        '%(asctime)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Request log file handler (only if file logging is available)
    if REQUEST_LOG_FILE is not None:
        try:
            # Check if request log file is locked
            request_path = Path(REQUEST_LOG_FILE)
            if request_path.exists() and _is_file_locked(request_path):
                # Skip request file handler if locked
                pass
            else:
                class SafeRotatingFileHandler(RotatingFileHandler):
                    def doRollover(self):
                        """Override to add lock checking before rotation"""
                        try:
                            if self.baseFilename and _is_file_locked(Path(self.baseFilename)):
                                return
                            if self.stream is None:
                                return
                            try:
                                if self.stream.tell() < self.maxBytes:
                                    return
                            except (OSError, AttributeError):
                                pass
                            super().doRollover()
                        except (OSError, PermissionError, IOError):
                            # Rotation failed silently - file is likely locked
                            pass
                        except Exception:
                            # Unexpected error - suppress
                            pass
                
                request_handler = SafeRotatingFileHandler(
                    REQUEST_LOG_FILE,
                    maxBytes=10 * 1024 * 1024,  # 10MB
                    backupCount=5,
                    encoding='utf-8',
                    delay=True
                )
                request_handler.setLevel(logging.INFO)
                request_handler.setFormatter(request_formatter)
                logger.addHandler(request_handler)
        except (OSError, PermissionError) as e:
            # If file logging fails, just use console (don't fail the app)
            pass
    
    # Also log to console (info and above)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(request_formatter)
    logger.addHandler(console_handler)
    
    return logger

# Create default logger for the application
default_logger = setup_logger("ocrd_extractor")

# Install custom error handler to suppress log rotation PermissionErrors
_original_handle_error = logging.Handler.handleError

def _suppress_rotation_errors(self, record):
    """Custom error handler that suppresses PermissionErrors from log rotation"""
    try:
        if record.exc_info and record.exc_info[0] == PermissionError:
            error_msg = str(record.getMessage())
            if 'log' in error_msg.lower() and ('rotate' in error_msg.lower() or 'rollover' in error_msg.lower()):
                return  # Suppress this error
        if "Logging error" in record.getMessage():
            return  # Suppress "Logging error" messages
    except:
        pass
    # Call original handler for other errors
    _original_handle_error(self, record)

# Monkey-patch the Handler class to use our custom error handler
logging.Handler.handleError = _suppress_rotation_errors
