import re
from typing import List, Dict, Optional, Tuple
from ..models.catalog_models import (
    ClassificationRequest, 
    ClassificationResult, 
    CatalogItem,
    InvestmentOffering
)
from .catalog_service import CatalogService
from .embedding_service import EmbeddingService
from ..utils.logger import setup_logger

logger = setup_logger(__name__)


class ClassificationService:
    """Service for classifying documents against investment catalog"""
    
    def __init__(self, catalog_service: Optional[CatalogService] = None):
        """
        Initialize classification service
        
        Args:
            catalog_service: CatalogService instance. If None, creates a new one.
        """
        self.catalog_service = catalog_service or CatalogService()
        self.embedding_service = EmbeddingService()
        self._catalog_index = None
        self._rebuild_index()
    
    def _rebuild_index(self):
        """Rebuild the embedding index from catalog"""
        try:
            catalog_items = self.catalog_service.get_catalog_for_indexing()
            if catalog_items:
                texts, meta, embeddings = self.embedding_service.build_catalog_index(catalog_items)
                self._catalog_index = {
                    "texts": texts,
                    "meta": meta,
                    "embeddings": embeddings,
                    "items": {item["id"]: item["item"] for item in catalog_items}
                }
                logger.info(f"✅ Rebuilt catalog index with {len(catalog_items)} items")
            else:
                logger.warning("⚠️ No catalog items to index")
                self._catalog_index = None
        except Exception as e:
            logger.error(f"❌ Failed to rebuild index: {e}")
            self._catalog_index = None
    
    def classify_document(self, request: ClassificationRequest) -> ClassificationResult:
        """
        Classify a document against the investment catalog
        
        Args:
            request: Classification request with document text
        
        Returns:
            ClassificationResult with decision and reasoning
        """
        if not self._catalog_index:
            return ClassificationResult(
                decision="NO",
                reason="Catalog is empty or index failed to build",
                matched_offering=None,
                similarity_score=None
            )
        
        # Extract candidate phrases from document
        candidates = self.embedding_service.extract_candidates(request.document_text)
        logger.debug(f"📝 Extracted {len(candidates)} candidate phrases")
        
        if not candidates:
            return ClassificationResult(
                decision="NO",
                reason="No relevant investment phrases found in document",
                matched_offering=None,
                candidate_phrases=[]
            )
        
        # Find best match for each candidate
        best_match = None
        all_matches = []
        
        for phrase in candidates:
            match_id, combined_score, emb_score, fuzzy_score = self.embedding_service.match_candidate(
                phrase,
                self._catalog_index["texts"],
                self._catalog_index["meta"],
                self._catalog_index["embeddings"],
                request.similarity_threshold
            )
            
            if match_id and combined_score >= request.similarity_threshold:
                all_matches.append({
                    "phrase": phrase,
                    "match_id": match_id,
                    "score": combined_score,
                    "embedding_score": emb_score,
                    "fuzzy_score": fuzzy_score
                })
                
                if best_match is None or combined_score > best_match["score"]:
                    best_match = {
                        "phrase": phrase,
                        "match_id": match_id,
                        "score": combined_score
                    }
        
        # If no matches above threshold
        if not best_match:
            return ClassificationResult(
                decision="NO",
                reason=f"No catalog items matched above threshold ({request.similarity_threshold:.2f})",
                matched_offering=None,
                similarity_score=None,
                candidate_phrases=candidates[:10]  # Return top 10 candidates
            )
        
        # Get the matched offering
        matched_item = self._catalog_index["items"].get(best_match["match_id"])
        if not matched_item:
            return ClassificationResult(
                decision="NO",
                reason=f"Matched catalog item '{best_match['match_id']}' not found",
                matched_offering=None,
                similarity_score=best_match["score"]
            )
        
        matched_offering = CatalogItem(**matched_item.model_dump())
        
        # Check for ambiguous matches (multiple close scores)
        close_matches = [
            m for m in all_matches 
            if m["match_id"] != best_match["match_id"] 
            and abs(m["score"] - best_match["score"]) < 0.1
        ]
        
        if close_matches and len(close_matches) > 0:
            ambiguous_items = []
            for m in close_matches[:2]:  # Top 2 ambiguous matches
                item = self._catalog_index["items"].get(m["match_id"])
                if item:
                    ambiguous_items.append(CatalogItem(**item.model_dump()))
            
            if ambiguous_items:
                return ClassificationResult(
                    decision="NEEDS_CLARIFICATION",
                    reason=f"Multiple close matches found. Please clarify which investment type is intended.",
                    matched_offering=matched_offering,
                    similarity_score=best_match["score"],
                    candidate_phrases=[best_match["phrase"]] + [m["phrase"] for m in close_matches[:2]],
                    ambiguous_matches=ambiguous_items
                )
        
        # Evaluate constraints if required
        constraint_violations = []
        if request.require_constraints:
            violations = self._evaluate_constraints(matched_item, request.document_text)
            constraint_violations = violations
        
        # Make final decision
        if constraint_violations:
            reason = f"Matches '{matched_offering.label}' but violates constraints: {', '.join(constraint_violations)}"
            return ClassificationResult(
                decision="NO",
                reason=reason,
                matched_offering=matched_offering,
                similarity_score=best_match["score"],
                constraint_violations=constraint_violations,
                candidate_phrases=[best_match["phrase"]]
            )
        else:
            reason = f"Matches '{matched_offering.label}' via phrase '{best_match['phrase']}'. Supported instrument types and regions."
            return ClassificationResult(
                decision="YES",
                reason=reason,
                matched_offering=matched_offering,
                similarity_score=best_match["score"],
                candidate_phrases=[best_match["phrase"]]
            )
    
    def _evaluate_constraints(
        self, 
        offering: InvestmentOffering, 
        document_text: str
    ) -> List[str]:
        """
        Evaluate business constraints against document text
        
        Args:
            offering: The matched investment offering
            document_text: The document text to check
        
        Returns:
            List of constraint violation messages (empty if all pass)
        """
        violations = []
        text_lower = document_text.lower()
        constraints = offering.constraints
        
        # Check investor types
        if constraints.investor_types:
            # Look for retail/consumer mentions
            if any(word in text_lower for word in ["retail", "consumer", "individual investor"]):
                if not any(it in constraints.investor_types for it in ["retail", "consumer"]):
                    violations.append("Retail investors not supported (only professional/institutional)")
        
        # Check ticket size
        if constraints.min_ticket_eur:
            # Extract monetary values from text
            patterns = [
                r"(\d[\d,\.]{2,})\s*(eur|€|euros?)",
                r"(eur|€|euros?)\s*(\d[\d,\.]{2,})",
                r"(\d[\d,\.]{2,})\s*(thousand|k|million|m)\s*(eur|€)?"
            ]
            
            min_found = None
            for pattern in patterns:
                matches = re.finditer(pattern, text_lower, re.IGNORECASE)
                for match in matches:
                    try:
                        # Extract number
                        num_str = match.group(1) if match.group(1) else match.group(2)
                        num_str = num_str.replace(",", "").replace(".", "")
                        value = float(num_str)
                        
                        # Handle multipliers
                        if "thousand" in match.group(0) or "k" in match.group(0):
                            value *= 1000
                        elif "million" in match.group(0) or "m" in match.group(0):
                            value *= 1000000
                        
                        if min_found is None or value < min_found:
                            min_found = value
                    except (ValueError, IndexError):
                        continue
            
            if min_found and min_found < constraints.min_ticket_eur:
                violations.append(
                    f"Ticket size €{min_found:,.0f} below minimum €{constraints.min_ticket_eur:,.0f}"
                )
        
        # Check regions (basic check)
        if constraints.regions:
            # Look for region mentions
            region_mentions = []
            for region in constraints.regions:
                if region.lower() in text_lower:
                    region_mentions.append(region)
            
            # If document mentions regions not in allowed list, flag it
            # (This is a simple check - could be enhanced)
            if "us" in text_lower or "united states" in text_lower:
                if "US" not in constraints.regions:
                    violations.append("US region not supported")
            elif "eu" in text_lower or "europe" in text_lower:
                if "EU" not in constraints.regions:
                    violations.append("EU region not supported")
        
        # Check instrument types (basic check)
        if constraints.instrument_types:
            # Look for instrument mentions
            instrument_mentions = []
            for inst_type in constraints.instrument_types:
                if inst_type.lower() in text_lower:
                    instrument_mentions.append(inst_type)
            
            # If document mentions instruments not in allowed list, could flag
            # (This is optional - document might mention multiple types)
        
        return violations

