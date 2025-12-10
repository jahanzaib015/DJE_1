"""
Pydantic models for LLM response validation
Replaces manual validation with type-safe models
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


class SectorRule(BaseModel):
    """Rule about investment sectors"""
    sector: str = Field(..., description="Sector name (e.g., 'Energy', 'Tobacco')")
    allowed: bool = Field(..., description="Whether investments in this sector are allowed")
    reason: str = Field(..., description="Reason or quote from document supporting this rule")
    
    @field_validator('sector')
    @classmethod
    def validate_sector(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Sector name cannot be empty")
        return v.strip()
    
    @field_validator('reason')
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Reason cannot be empty")
        return v.strip()


class CountryRule(BaseModel):
    """Rule about investment countries/regions"""
    country: str = Field(..., description="Country or region name")
    allowed: bool = Field(..., description="Whether investments in this country are allowed")
    reason: str = Field(..., description="Reason or quote from document supporting this rule")
    
    @field_validator('country')
    @classmethod
    def validate_country(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Country name cannot be empty")
        return v.strip()
    
    @field_validator('reason')
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Reason cannot be empty")
        return v.strip()


class InstrumentRule(BaseModel):
    """Rule about financial instruments"""
    instrument: str = Field(..., description="Instrument name (e.g., 'bonds', 'stocks', 'derivatives')")
    allowed: bool = Field(..., description="Whether this instrument is allowed")
    reason: str = Field(..., description="Reason or quote from document supporting this rule")
    
    @field_validator('instrument')
    @classmethod
    def validate_instrument(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Instrument name cannot be empty")
        return v.strip()
    
    @field_validator('reason')
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Reason cannot be empty")
        return v.strip()


class Conflict(BaseModel):
    """Conflict or unclear information in the document"""
    category: str = Field(..., description="Category of conflict (e.g., 'system_error', 'parsing_error', 'contradiction')")
    detail: str = Field(..., description="Details about the conflict")
    
    @field_validator('category')
    @classmethod
    def validate_category(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Conflict category cannot be empty")
        return v.strip()


class LLMResponse(BaseModel):
    """Complete LLM response structure with validation"""
    sector_rules: List[SectorRule] = Field(default_factory=list, description="Rules about investment sectors")
    country_rules: List[CountryRule] = Field(default_factory=list, description="Rules about investment countries")
    instrument_rules: List[InstrumentRule] = Field(default_factory=list, description="Rules about financial instruments")
    conflicts: List[Conflict] = Field(default_factory=list, description="Conflicts or errors found")
    
    @classmethod
    def from_dict(cls, data: dict) -> 'LLMResponse':
        """Create LLMResponse from dictionary with validation"""
        try:
            return cls(**data)
        except Exception as e:
            # Provide helpful error message
            raise ValueError(f"Invalid LLM response structure: {str(e)}")
    
    def to_dict(self) -> dict:
        """Convert to dictionary (for backward compatibility)"""
        return self.model_dump()
    
    def normalize(self) -> 'LLMResponse':
        """Normalize the response (already validated, just return self)"""
        return self






