from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class InvestmentConstraints(BaseModel):
    """Business constraints for an investment offering"""
    instrument_types: Optional[List[str]] = Field(default=None, description="Allowed instrument types (e.g., ['physical', 'etf', 'cfds'])")
    regions: Optional[List[str]] = Field(default=None, description="Allowed regions (e.g., ['EU', 'US'])")
    investor_types: Optional[List[str]] = Field(default=None, description="Allowed investor types (e.g., ['professional', 'institutional', 'retail'])")
    min_ticket_eur: Optional[float] = Field(default=None, description="Minimum ticket size in EUR")
    max_ticket_eur: Optional[float] = Field(default=None, description="Maximum ticket size in EUR")
    regulatory_tags: Optional[List[str]] = Field(default=None, description="Regulatory tags (e.g., ['UCITS', 'AIF'])")
    other_constraints: Optional[Dict[str, Any]] = Field(default=None, description="Additional custom constraints")


class InvestmentOffering(BaseModel):
    """Model for an investment offering in the catalog"""
    id: str = Field(..., description="Unique identifier for the offering")
    label: str = Field(..., description="Canonical label/name")
    synonyms: List[str] = Field(default_factory=list, description="List of synonyms and alternative names")
    description: str = Field(..., description="Description of the offering")
    constraints: InvestmentConstraints = Field(default_factory=InvestmentConstraints, description="Business constraints")
    active: bool = Field(default=True, description="Whether this offering is currently active")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class CatalogItem(BaseModel):
    """Response model for catalog items"""
    id: str
    label: str
    synonyms: List[str]
    description: str
    constraints: InvestmentConstraints
    active: bool
    metadata: Optional[Dict[str, Any]] = None


class ClassificationRequest(BaseModel):
    """Request model for document classification"""
    document_text: str = Field(..., description="The document text to classify")
    document_metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional metadata about the document")
    similarity_threshold: float = Field(default=0.68, ge=0.0, le=1.0, description="Minimum similarity score for matching")
    require_constraints: bool = Field(default=True, description="Whether to enforce constraint checking")


class ClassificationResult(BaseModel):
    """Result model for document classification"""
    decision: str = Field(..., description="YES, NO, or NEEDS_CLARIFICATION")
    reason: str = Field(..., description="One-line explanation of the decision")
    matched_offering: Optional[CatalogItem] = Field(default=None, description="The matched catalog item if found")
    similarity_score: Optional[float] = Field(default=None, description="Similarity score (0-1)")
    constraint_violations: List[str] = Field(default_factory=list, description="List of constraint violations if any")
    candidate_phrases: List[str] = Field(default_factory=list, description="Key phrases extracted from document")
    ambiguous_matches: Optional[List[CatalogItem]] = Field(default=None, description="Multiple close matches if decision is NEEDS_CLARIFICATION")

