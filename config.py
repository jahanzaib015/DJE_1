import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Server Configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

# File Upload Configuration
MAX_FILE_SIZE = os.getenv("MAX_FILE_SIZE", "50MB")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
EXPORT_DIR = os.getenv("EXPORT_DIR", "exports")

# LLM Configuration
DEFAULT_LLM_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "openai")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4")
DEFAULT_ANALYSIS_METHOD = os.getenv("DEFAULT_ANALYSIS_METHOD", "llm_with_fallback")
