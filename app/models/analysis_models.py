from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from enum import Enum

class AnalysisMethod(str, Enum):
    KEYWORDS = "keywords"
    LLM = "llm"
    LLM_WITH_FALLBACK = "llm_with_fallback"

class LLMProvider(str, Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"
    CLAUDE = "claude"

class AnalysisRequest(BaseModel):
    file_path: str
    analysis_method: AnalysisMethod = AnalysisMethod.LLM_WITH_FALLBACK
    llm_provider: LLMProvider = LLMProvider.OPENAI
    model: str = "gpt-4"
    fund_id: str = "5800"

class JobStatus(BaseModel):
    job_id: str
    status: str  # queued, processing, completed, failed
    progress: int  # 0-100
    message: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str = None

class AnalysisResult(BaseModel):
    fund_id: str
    analysis_method: str
    llm_provider: str
    model: str
    total_instruments: int
    allowed_instruments: int
    evidence_coverage: int
    sections: Dict[str, Any]
    processing_time: float
    created_at: str

class InstrumentData(BaseModel):
    allowed: bool
    note: str
    evidence: Dict[str, str]
