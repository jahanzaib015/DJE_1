"""
Centralized logging configuration for the OCRD Extractor backend.
Provides structured logging with file and console handlers.
"""
import logging
import os
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
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Console handler (always show)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (detailed logs) - only if file logging is available
    if log_file is None:
        log_file = LOG_FILE
    
    if log_file is not None:
        try:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(detailed_formatter)
            logger.addHandler(file_handler)
        except (OSError, PermissionError) as e:
            # If file logging fails, just use console (don't fail the app)
            logger.warning(f"Could not create file handler: {e}. Using console logging only.")
    
    # Error file handler (only errors and above)
    if ERROR_LOG_FILE is not None:
        try:
            error_handler = RotatingFileHandler(
                ERROR_LOG_FILE,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
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
            request_handler = RotatingFileHandler(
                REQUEST_LOG_FILE,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            request_handler.setLevel(logging.INFO)
            request_handler.setFormatter(request_formatter)
            logger.addHandler(request_handler)
        except (OSError, PermissionError) as e:
            # If file logging fails, just use console (don't fail the app)
            pass
    
    # Also log to console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(request_formatter)
    logger.addHandler(console_handler)
    
    return logger

# Create default logger for the application
default_logger = setup_logger("ocrd_extractor")

