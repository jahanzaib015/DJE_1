from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime

class AnalysisMethod(str, Enum):
    KEYWORDS = "keywords"
    LLM = "llm"
    LLM_WITH_FALLBACK = "llm_with_fallback"

class LLMProvider(str, Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"
    CLAUDE = "claude"

class AnalysisRequest(BaseModel):
    """Request model for document analysis"""
    model_config = ConfigDict(
        # Allow string values to be converted to enums automatically
        use_enum_values=True,
        # Be more lenient with validation
        validate_assignment=False,
        # Allow extra fields (in case frontend sends extra data)
        extra='ignore'
    )
    
    file_path: str = Field(..., description="Path to the PDF file to analyze")
    analysis_method: Optional[AnalysisMethod] = Field(
        default=AnalysisMethod.LLM,
        description="Analysis method to use"
    )
    llm_provider: Optional[LLMProvider] = Field(
        default=LLMProvider.OPENAI,
        description="LLM provider to use"
    )
    model: Optional[str] = Field(
        default="gpt-5",
        description="Specific model to use (e.g., 'gpt-5', 'gpt-4o', 'gpt-4o-mini')"
    )
    fund_id: Optional[str] = Field(
        default="5800",
        description="Fund identifier for the analysis"
    )
    
    @field_validator('file_path', mode='before')
    @classmethod
    def validate_file_path(cls, v) -> str:
        if v is None:
            raise ValueError("File path cannot be empty")
        v_str = str(v).strip()
        if not v_str:
            raise ValueError("File path cannot be empty")
        # Allow any file path (not just .pdf) for flexibility
        return v_str
    
    @field_validator('analysis_method', mode='before')
    @classmethod
    def validate_analysis_method(cls, v) -> Optional[AnalysisMethod]:
        """Convert string to enum, allowing both string and enum values"""
        if v is None:
            return AnalysisMethod.LLM
        if isinstance(v, AnalysisMethod):
            return v
        if isinstance(v, str):
            try:
                return AnalysisMethod(v.lower())
            except ValueError:
                # Default to LLM if invalid
                return AnalysisMethod.LLM
        return AnalysisMethod.LLM
    
    @field_validator('llm_provider', mode='before')
    @classmethod
    def validate_llm_provider(cls, v) -> Optional[LLMProvider]:
        """Convert string to enum, allowing both string and enum values"""
        if v is None:
            return LLMProvider.OPENAI
        if isinstance(v, LLMProvider):
            return v
        if isinstance(v, str):
            try:
                return LLMProvider(v.lower())
            except ValueError:
                # Default to OPENAI if invalid
                return LLMProvider.OPENAI
        return LLMProvider.OPENAI
    
    @field_validator('model')
    @classmethod
    def validate_model(cls, v: str) -> str:
        if not v or not str(v).strip():
            return "gpt-5"  # Default model
        # Supported models: gpt-5, gpt-4o, gpt-4o-mini, o1, o1-mini
        # Note: Deprecated models (gpt-4, gpt-4-turbo, gpt-3.5-turbo) removed
        v_str = str(v).strip()
        # Allow any model (for future models), just normalize
        return v_str

class JobStatus(BaseModel):
    """Status model for analysis jobs"""
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Job status: queued, processing, completed, or failed")
    progress: int = Field(..., ge=0, le=100, description="Progress percentage (0-100)")
    message: str = Field(..., description="Status message")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Analysis result if completed")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    created_at: Optional[str] = Field(default=None, description="ISO timestamp when job was created")
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid_statuses = ["queued", "processing", "completed", "failed"]
        if v.lower() not in valid_statuses:
            raise ValueError(f"Status must be one of: {valid_statuses}")
        return v.lower()
    
    @field_validator('created_at', mode='before')
    @classmethod
    def set_created_at(cls, v):
        if v is None:
            return datetime.now().isoformat()
        return v

class AnalysisResult(BaseModel):
    fund_id: str
    analysis_method: str
    llm_provider: str
    model: str
    total_instruments: int
    allowed_instruments: int
    evidence_coverage: int
    confidence_score: int
    sections: Dict[str, Any]
    processing_time: float
    created_at: str

class InstrumentData(BaseModel):
    allowed: bool
    note: str
    evidence: Dict[str, str]
