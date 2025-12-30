import os
import re
import time
import uuid
import asyncio
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
from .llm_service import LLMService
from .rag_retrieve import retrieve_rules
from .rag_index import build_chunks
from .excel_mapping_service import ExcelMappingService
from .conservative_classifier import build_items_hits, decide
from ..models.analysis_models import AnalysisResult, AnalysisMethod, LLMProvider, AnalysisRequest
from ..models.llm_response_models import LLMResponse
from ..utils.trace_handler import TraceHandler
from ..utils.file_handler import FileHandler
from ..utils.logger import setup_logger

logger = setup_logger(__name__)

def get_enum_value(value):
    """Safely get enum value, handling both enum objects and strings"""
    if hasattr(value, 'value'):
        return value.value
    return str(value)

class AnalysisService:
    """Core analysis service that orchestrates document analysis"""
    
    def __init__(self, excel_mapping_path: Optional[str] = None):
        try:
            self.llm_service = LLMService()
        except Exception as e:
            logger.warning(f"Failed to initialize LLMService in AnalysisService: {e}")
            self.llm_service = None
        self.trace_handler = TraceHandler()
        self.file_handler = FileHandler()
        
        # Initialize Excel mapping service
        try:
            self.excel_mapping = ExcelMappingService(excel_path=excel_mapping_path)
            logger.info(f"Excel mapping service initialized with {len(self.excel_mapping.get_all_entries())} entries")
        except Exception as e:
            logger.warning(f"Failed to initialize ExcelMappingService: {e}")
            self.excel_mapping = None
    
    async def analyze_document(
        self, 
        text: str, 
        analysis_method: AnalysisMethod,
        llm_provider: LLMProvider,
        model: str,
        fund_id: str,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Main analysis method that coordinates different analysis approaches"""
        
        # Early validation: Check if LLM service is available
        if not self.llm_service:
            error_msg = "LLMService is not initialized. Cannot perform document analysis. Please check your configuration."
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # For very large documents, we'll use chunked processing to avoid memory issues
        # But we'll process ALL text, not truncate
        VERY_LARGE_DOCUMENT_THRESHOLD = 200000  # 200KB - use chunked processing
        use_chunked_processing = len(text) > VERY_LARGE_DOCUMENT_THRESHOLD
        
        logger.info(f"Document size: {len(text)} characters ({len(text)/1024:.1f} KB)")
        
        start_time = time.time()
        
        # Create empty OCRD structure
        data = self._create_empty_ocrd_json(fund_id)
        
        # NEW: Apply conservative, evidence-based classification
        if self.excel_mapping:
            logger.info("🔍 Step 1: Applying conservative, evidence-based classification...")
            try:
                # Get term_map from Excel mapping
                term_map = self.excel_mapping.get_term_map()
                
                if term_map:
                    # Build items_hits by scanning text sentence-by-sentence
                    items_hits = build_items_hits(text, term_map)
                    
                    logger.info(f"   📊 Found {sum(len(hits) for hits in items_hits.values())} total evidence hits across {len(items_hits)} terms")
                    
                    # Apply conservative classification
                    decisions, evidence = decide(items_hits, term_map)
                    
                    # Update Excel mapping entries with conservative decisions
                    for term, status in decisions.items():
                        # Map status to allowed boolean
                        if status == "Allowed":
                            allowed = True
                        elif status == "Prohibited":
                            allowed = False
                        else:  # Conditional or Review
                            allowed = None  # Mark for manual review
                        
                        # Update Excel entry
                        evid_text = evidence.get(term, "")[:300]  # Limit evidence to 300 chars
                        self.excel_mapping.update_entry_by_instrument(term, allowed, evid_text)
                    
                    allowed_count = sum(1 for s in decisions.values() if s == "Allowed")
                    prohibited_count = sum(1 for s in decisions.values() if s == "Prohibited")
                    conditional_count = sum(1 for s in decisions.values() if s == "Conditional")
                    review_count = sum(1 for s in decisions.values() if s == "Review")
                    
                    logger.info(f"✅ Conservative classification complete: {allowed_count} Allowed, {prohibited_count} Prohibited, {conditional_count} Conditional, {review_count} Review")
                else:
                    logger.warning("⚠️ No term_map available - skipping conservative classification")
            except Exception as e:
                logger.error(f"Error in conservative classification: {e}", exc_info=True)
                # Continue with LLM analysis even if conservative classification fails
        
        # NEW: Search document text for ALL Excel entries (Column A) and use LLM to determine allowed/prohibited
        # Add timeout to prevent hanging on large Excel files
        if self.excel_mapping and self.llm_service:
            logger.info("Step 2: Searching document for Excel entries using LLM analysis...")
            try:
                # Limit Excel search time to prevent crashes (5 minutes max)
                search_stats = await asyncio.wait_for(
                    self.excel_mapping.search_document_with_llm(
                        text, 
                        self.llm_service, 
                        get_enum_value(llm_provider), 
                        model
                    ),
                    timeout=300.0  # 5 minutes max
                )
                logger.info(f"LLM search complete: {search_stats['matches_found']} Excel entries found, {search_stats['allowed_found']} allowed, {search_stats['prohibited_found']} prohibited")
            except asyncio.TimeoutError:
                logger.warning("Excel mapping LLM search timed out - continuing with main analysis")
            except Exception as e:
                logger.warning(f"Excel mapping LLM search failed: {e} - continuing with main analysis")
        elif self.excel_mapping and not self.llm_service:
            logger.debug("Skipping Excel mapping LLM search: LLM service not available")
        
        # ONLY USE LLM ANALYSIS - No keyword analysis or fallback
        # All analysis methods use LLM only
        if trace_id:
            result, raw_analysis = await self._analyze_with_llm_traced(data, text, llm_provider, model, trace_id)
        else:
            result, raw_analysis = await self._analyze_with_llm(data, text, llm_provider, model, trace_id)
        analysis_method_used = f"llm_{get_enum_value(llm_provider)}"
        
        processing_time = time.time() - start_time
        
        # Calculate metrics
        total_instruments, allowed_instruments, evidence_coverage = self._calculate_metrics(result)
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(
            result, 
            evidence_coverage, 
            model,
            raw_analysis
        )
        
        return {
            "fund_id": fund_id,
            "analysis_method": analysis_method_used,
            "llm_provider": get_enum_value(llm_provider),
            "model": model,
            "total_instruments": total_instruments,
            "allowed_instruments": allowed_instruments,
            "evidence_coverage": evidence_coverage,
            "confidence_score": confidence_score,
            "sections": result["sections"],
            "notes": result.get("notes", []),  # Include debug notes in response
            "processing_time": round(processing_time, 2),
            "created_at": datetime.now().isoformat()
        }
    
    def map_rows_to_excel(self, rows: List[Dict], fund_id: str) -> Dict[str, Any]:
        """
        Map vision-extracted rows to Excel instruments using fuzzy matching.
        
        Args:
            rows: List of rows from vision extraction, each with:
                - "instrument": instrument name
                - "allowed": True/False
                - "section": section name
                - "details": detail restrictions
            fund_id: Fund ID for tracking
            
        Returns:
            Dict with mapping statistics and updated Excel entries
        """
        if not self.excel_mapping:
            logger.warning("⚠️ Excel mapping service not available - skipping row mapping")
            return {"mapped": 0, "total_rows": len(rows), "errors": []}
        
        mapped_count = 0
        errors = []
        all_entries = self.excel_mapping.get_all_entries()
        
        # Try to import rapidfuzz for fuzzy matching
        try:
            from rapidfuzz import fuzz
            RAPIDFUZZ_AVAILABLE = True
        except ImportError:
            RAPIDFUZZ_AVAILABLE = False
            logger.warning("⚠️ rapidfuzz not available - using basic string matching")
        
        logger.info(f"🔍 Mapping {len(rows)} vision-extracted rows to {len(all_entries)} Excel instruments...")
        
        for row_idx, row in enumerate(rows, 1):
            instrument_name = row.get("instrument", "").strip()
            allowed = row.get("allowed", False)
            section = row.get("section", "")
            details = row.get("details", "")
            
            if not instrument_name:
                errors.append(f"Row {row_idx}: Empty instrument name")
                continue
            
            # Build reason string
            reason = f"Vision extraction: Section {section}"
            if details:
                reason += f". {details}"
            
            # Try to find matching Excel entry
            matched = False
            
            # Method 1: Use Excel mapping's find_matching_entries (already has fuzzy logic)
            matching_entries = self.excel_mapping.find_matching_entries(instrument_name)
            
            if matching_entries:
                # Use the first/best match
                best_match = matching_entries[0]
                self.excel_mapping.update_allowed_status(
                    best_match['row_id'],
                    allowed,
                    reason
                )
                mapped_count += 1
                matched = True
                logger.debug(f"✅ Row {row_idx}: '{instrument_name}' -> '{best_match['instrument_category']}' (allowed={allowed})")
            else:
                # Method 2: Direct fuzzy matching against all entries
                if RAPIDFUZZ_AVAILABLE:
                    best_score = 0.0
                    best_entry = None
                    
                    for entry in all_entries:
                        entry_name = entry.get('instrument_category', '').strip()
                        if not entry_name:
                            continue
                        
                        # Calculate fuzzy match score
                        score = fuzz.partial_ratio(instrument_name.lower(), entry_name.lower()) / 100.0
                        
                        # Also try token-based matching
                        token_score = fuzz.token_sort_ratio(instrument_name.lower(), entry_name.lower()) / 100.0
                        score = max(score, token_score)
                        
                        if score > best_score and score >= 0.75:  # 75% similarity threshold
                            best_score = score
                            best_entry = entry
                    
                    if best_entry:
                        self.excel_mapping.update_allowed_status(
                            best_entry['row_id'],
                            allowed,
                            reason
                        )
                        mapped_count += 1
                        matched = True
                        logger.info(f"✅ Row {row_idx}: '{instrument_name}' -> '{best_entry['instrument_category']}' (fuzzy match: {best_score:.0%}, allowed={allowed})")
                    else:
                        errors.append(f"Row {row_idx}: '{instrument_name}' - No match found (best score < 75%)")
                else:
                    # Fallback: simple substring matching
                    for entry in all_entries:
                        entry_name = entry.get('instrument_category', '').strip().lower()
                        if not entry_name:
                            continue
                        
                        if instrument_name.lower() in entry_name or entry_name in instrument_name.lower():
                            self.excel_mapping.update_allowed_status(
                                entry['row_id'],
                                allowed,
                                reason
                            )
                            mapped_count += 1
                            matched = True
                            logger.info(f"✅ Row {row_idx}: '{instrument_name}' -> '{entry['instrument_category']}' (substring match, allowed={allowed})")
                            break
                    
                    if not matched:
                        errors.append(f"Row {row_idx}: '{instrument_name}' - No match found")
            
            if not matched:
                logger.warning(f"⚠️ Row {row_idx}: Could not map '{instrument_name}' to any Excel instrument")
        
        logger.info(f"✅ Mapping complete: {mapped_count}/{len(rows)} rows mapped to Excel instruments")
        if errors:
            logger.warning(f"⚠️ {len(errors)} rows could not be mapped")
        
        return {
            "mapped": mapped_count,
            "total_rows": len(rows),
            "errors": errors,
            "fund_id": fund_id
        }
    
    async def analyze_document_vision(
        self,
        pdf_path: str,
        analysis_method: AnalysisMethod,
        llm_provider: LLMProvider,
        model: str,
        fund_id: str,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze image-only PDF using vision models.
        
        This method is called when an image-only (scanned) PDF is detected.
        It uses vision-capable LLMs to read tables and extract investment rules.
        """
        start_time = time.time()
        
        # Create empty OCRD structure
        data = self._create_empty_ocrd_json(fund_id)
        
        # Check if LLM service is available
        if not self.llm_service:
            error_msg = "LLMService is not initialized. Cannot perform vision analysis."
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
        
        # Use vision-based LLM analysis
        logger.info(f"🔍 Starting vision-based LLM analysis with {get_enum_value(llm_provider)}/{model}")
        
        if trace_id:
            analysis = await self.llm_service.analyze_document_vision(
                pdf_path, get_enum_value(llm_provider), model, trace_id
            )
        else:
            analysis = await self.llm_service.analyze_document_vision(
                pdf_path, get_enum_value(llm_provider), model, None
            )
        
        # Log what LLM returned
        if isinstance(analysis, dict):
            instrument_count = len(analysis.get("instrument_rules", []))
            sector_count = len(analysis.get("sector_rules", []))
            country_count = len(analysis.get("country_rules", []))
            allowed_count = sum(1 for r in analysis.get("instrument_rules", []) if r.get("allowed", False))
            logger.info(f"📊 Vision LLM returned: {instrument_count} instrument rules ({allowed_count} allowed), {sector_count} sector rules, {country_count} country rules")
            
            # Log raw_rows count if available
            if "raw_rows" in analysis:
                raw_allowed = sum(1 for r in analysis.get("raw_rows", []) if r.get("allowed", False))
                logger.info(f"📋 Raw rows from vision: {len(analysis.get('raw_rows', []))} rows ({raw_allowed} allowed)")
        
        # Extract raw rows from vision analysis response
        # The vision analysis returns raw_rows in the result structure
        raw_rows = []
        if isinstance(analysis, dict) and "raw_rows" in analysis:
            raw_rows = analysis.get("raw_rows", [])
        elif trace_id:
            # Fallback: Try to get raw_rows from trace file
            try:
                trace_dir = self.trace_handler.get_trace_dir(trace_id)
                llm_response_file = os.path.join(trace_dir, f"{trace_id}_llm_response.json")
                if os.path.exists(llm_response_file):
                    import json
                    with open(llm_response_file, 'r') as f:
                        trace_data = json.load(f)
                        if isinstance(trace_data, dict) and "raw_rows" in trace_data.get("result", {}):
                            raw_rows = trace_data["result"]["raw_rows"]
            except Exception as e:
                logger.debug(f"Could not load raw_rows from trace: {e}")
        
        # If we have raw_rows, map them to Excel first
        if raw_rows and self.excel_mapping:
            logger.info(f"🗺️ Mapping {len(raw_rows)} vision-extracted rows to Excel instruments...")
            mapping_result = self.map_rows_to_excel(raw_rows, fund_id)
            logger.info(f"✅ Excel mapping: {mapping_result['mapped']}/{mapping_result['total_rows']} rows mapped")
            if mapping_result['errors']:
                logger.warning(f"⚠️ {len(mapping_result['errors'])} rows could not be mapped: {mapping_result['errors'][:5]}")
        
        # Convert LLM response to OCRD format (same as text-based analysis)
        logger.info("🔄 Converting vision LLM response to OCRD format...")
        converted_data = self._convert_llm_response_to_ocrd_format(analysis, full_text="")
        converted_data["fund_id"] = data.get("fund_id", fund_id)
        data = converted_data
        
        processing_time = time.time() - start_time
        
        # Calculate metrics
        total_instruments, allowed_instruments, evidence_coverage = self._calculate_metrics(data)
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(
            data,
            evidence_coverage,
            model,
            analysis
        )
        
        return {
            "fund_id": fund_id,
            "analysis_method": f"vision_{get_enum_value(llm_provider)}",
            "llm_provider": get_enum_value(llm_provider),
            "model": model,
            "total_instruments": total_instruments,
            "allowed_instruments": allowed_instruments,
            "evidence_coverage": evidence_coverage,
            "confidence_score": confidence_score,
            "sections": data["sections"],
            "notes": data.get("notes", []),
            "processing_time": round(processing_time, 2),
            "created_at": datetime.now().isoformat()
        }
    
    async def analyze_document_rag(self, request: AnalysisRequest) -> Dict[str, Any]:
        """RAG-enhanced analysis method that uses document chunking and retrieval"""
        trace_id = str(uuid.uuid4())
        trace_handler = TraceHandler(trace_id)
        file_handler = FileHandler()

        try:
            # 1. Save uploaded PDF locally
            pdf_path = await file_handler.save_uploaded_file(request.file)
            trace_handler.log_step("file_saved", {"path": pdf_path})

            # 2. Extract raw text
            extracted_text = await file_handler.extract_pdf_text(pdf_path)
            trace_handler.log_step("text_extracted", {"length": len(extracted_text)})

            # 3. Chunk and build vector collection
            chunks = build_chunks(pdf_path, extracted_text)
            # Note: create_temp_collection method needs to be implemented in FileHandler
            # For now, we'll use the chunks directly
            trace_handler.log_step("collection_built", {"chunks": len(chunks)})

            # 4. Retrieve relevant context for this query
            user_query = "List all rules about allowed and restricted investment sectors, countries, and instruments."
            # Note: retrieve_rules expects a collection parameter, we'll adapt this
            # For now, we'll use the chunks directly as context
            results = {"documents": [chunks]}  # Simplified for now
            trace_handler.log_retrieval(results["documents"])

            # 5. Format retrieved context for LLM
            retrieved_chunks = [chunk for sublist in results["documents"] for chunk in sublist]
            combined_context = "\n\n".join(getattr(c, "text", str(c)) for c in retrieved_chunks)

            # ===== DEBUG: CHUNK COUNTS & CONTEXT LENGTH =====
            logger.info(
                "[RAG] job=%s fund=%s chunks=%d combined_context_len=%d",
                trace_id, request.fund_id, len(retrieved_chunks), len(combined_context)
            )

            # optional: peek at the first 2 chunks
            for i, ch in enumerate(retrieved_chunks[:2]):
                preview = getattr(ch, "text", "")[:200].replace("\n", " ")
                logger.info("[RAG] job=%s top%d score=%s preview=%r",
                            trace_id, i+1, getattr(ch, "score", None), preview)

            # also write the actual prompt context to traces so you can open it
            trace_dir = trace_handler.get_trace_dir(trace_id)
            os.makedirs(trace_dir, exist_ok=True)
            context_file_path = os.path.join(trace_dir, f"{trace_id}_context.txt")
            with open(context_file_path, 'w', encoding='utf-8') as f:
                f.write(combined_context)
            # ================================================

            # 6. Send to LLM
            llm_service = LLMService()
            # RAG system prompt for extraction (simpler version for RAG context)
            rag_system_prompt = f"""
            You are a compliance analyst. Based on the following policy text, extract explicit investment permissions or prohibitions.

            Context:
            {combined_context}
            """
            llm_response = await llm_service.analyze_document(rag_system_prompt, get_enum_value(request.llm_provider), request.model, trace_id)
            trace_handler.log_step("llm_response", {"length": len(str(llm_response))})

            # 7. Convert LLM output into structured format
            # Note: save_excel_from_json method needs to be implemented in FileHandler
            # For now, we'll return the structured response
            trace_handler.log_step("analysis_completed", {"trace_id": trace_id})

            return {
                "trace_id": trace_id, 
                "analysis_result": llm_response,
                "chunks_processed": len(chunks),
                "context_length": len(combined_context)
            }
            
        except Exception as e:
            trace_handler.log_error(f"RAG analysis failed: {str(e)}")
            raise Exception(f"RAG analysis failed: {str(e)}")
    
    def _split_document_into_sections(self, text: str, max_section_size: int = 27500, overlap: int = 2000) -> List[Dict[str, Any]]:
        """
        Split document into logical sections for per-section extraction.
        
        Strategy:
        1. First, try to detect logical section headers (German section headers, numbered sections)
        2. If no clear sections found, use semantic chunking with overlap
        3. Ensure sections don't exceed max_section_size to avoid token limits
        
        Args:
            text: Full document text
            max_section_size: Maximum characters per section (default 27.5k ≈ 4–6k tokens to leave room for prompts)
            overlap: Character overlap between sections to avoid missing items at boundaries
            
        Returns:
            List of section dicts with keys: 'section_id', 'title', 'text', 'start_char', 'end_char'
        """
        sections = []
        
        # German section headers to look for (case-insensitive)
        german_section_patterns = [
            r'(?i)^\s*(Zulässige\s+Anlagen?|Zulässige\s+Anlageinstrumente?)',
            r'(?i)^\s*(Unzulässige\s+Anlagen?|Unzulässige\s+Anlageinstrumente?)',
            r'(?i)^\s*(Erlaubte\s+Anlagen?|Erlaubte\s+Instrumente?)',
            r'(?i)^\s*(Verbotene\s+Anlagen?|Verbotene\s+Instrumente?)',
            r'(?i)^\s*(Zugelassene\s+Anlagen?|Zugelassene\s+Instrumente?)',
        ]
        
        # Common section header patterns (numbered sections, all caps, etc.)
        section_header_patterns = [
            r'^\s*\d+[\.\)]\s+[A-ZÄÖÜ][^\n]{5,100}',  # Numbered sections: "1. Section Title"
            r'^\s*[A-ZÄÖÜ][A-ZÄÖÜ\s]{5,50}:?\s*$',  # All caps headers
            r'^\s*[A-ZÄÖÜ][^\n]{5,100}\s*$',  # Title case headers on their own line
        ]
        
        # Combine all patterns
        all_patterns = german_section_patterns + section_header_patterns
        
        # Try to find section boundaries
        lines = text.split('\n')
        section_boundaries = [0]  # Start of document
        
        for i, line in enumerate(lines):
            # Check if this line matches any section header pattern
            for pattern in all_patterns:
                if re.search(pattern, line):
                    # Found a section header - mark this position
                    char_pos = len('\n'.join(lines[:i]))
                    if char_pos > section_boundaries[-1] + 1000:  # Only add if significant distance
                        section_boundaries.append(char_pos)
                    break
        
        # Add end of document
        section_boundaries.append(len(text))
        
        # If we found meaningful sections (more than just start/end), use them
        if len(section_boundaries) > 2:
            logger.info(f"📑 Found {len(section_boundaries)-1} logical sections based on headers")
            
            for i in range(len(section_boundaries) - 1):
                start = section_boundaries[i]
                end = section_boundaries[i + 1]
                
                # Extract section title (first line or nearby)
                section_text = text[start:end]
                first_lines = section_text.split('\n')[:3]
                title = first_lines[0].strip()[:100] if first_lines else f"Section {i+1}"
                
                # If section is too large, split it further
                if len(section_text) > max_section_size:
                    # Split large section into chunks
                    sub_sections = self._split_large_section(section_text, max_section_size, overlap, start)
                    sections.extend(sub_sections)
                else:
                    sections.append({
                        'section_id': i + 1,
                        'title': title,
                        'text': section_text,
                        'start_char': start,
                        'end_char': end
                    })
        else:
            # No clear sections found - use semantic chunking
            logger.info(f"📄 No clear section headers found, using semantic chunking")
            sections = self._split_large_section(text, max_section_size, overlap, 0)
            # Update titles
            for i, sec in enumerate(sections):
                sec['section_id'] = i + 1
                if not sec.get('title'):
                    sec['title'] = f"Chunk {i+1}"
        
        logger.info(f"✅ Document split into {len(sections)} sections for extraction")
        for i, sec in enumerate(sections[:5]):  # Log first 5
            logger.info(f"   Section {sec['section_id']}: '{sec['title'][:50]}' ({len(sec['text'])} chars)")
        if len(sections) > 5:
            logger.info(f"   ... and {len(sections) - 5} more sections")
        
        return sections
    
    def _split_large_section(self, text: str, max_size: int, overlap: int, base_offset: int) -> List[Dict[str, Any]]:
        """
        Split a large section into smaller chunks with overlap.
        
        Args:
            text: Text to split
            max_size: Maximum characters per chunk
            overlap: Character overlap between chunks
            base_offset: Character offset from document start
            
        Returns:
            List of section dicts
        """
        chunks = []
        start = 0
        chunk_id = 1
        
        while start < len(text):
            end = min(start + max_size, len(text))
            
            # Try to break at sentence boundary if not at end
            if end < len(text):
                # Look for sentence endings near the boundary
                boundary_text = text[max(0, end-200):end+200]
                sentence_end = max(
                    boundary_text.rfind('. '),
                    boundary_text.rfind('.\n'),
                    boundary_text.rfind('.\t'),
                )
                if sentence_end > 100:  # Found a good break point
                    end = end - 200 + sentence_end + 1
            
            chunk_text = text[start:end]
            
            # Extract a title from first line
            first_line = chunk_text.split('\n')[0].strip()[:100]
            title = first_line if first_line else f"Chunk {chunk_id}"
            
            chunks.append({
                'section_id': chunk_id,
                'title': title,
                'text': chunk_text,
                'start_char': base_offset + start,
                'end_char': base_offset + end
            })
            
            # Move start with overlap
            start = end - overlap if end < len(text) else end
            chunk_id += 1
        
        return chunks
    
    def _merge_section_results(self, section_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge extraction results from multiple sections.
        
        Strategy:
        - Combine all instrument_rules, sector_rules, country_rules
        - Handle duplicates: if same instrument appears multiple times:
          * Prohibited overrides Allowed
          * If both are Allowed or both Prohibited, keep the one with more detailed reason
        - Combine conflicts
        
        Args:
            section_results: List of analysis dicts from each section
            
        Returns:
            Merged analysis dict
        """
        merged = {
            "instrument_rules": [],
            "sector_rules": [],
            "country_rules": [],
            "conflicts": []
        }
        
        # Track seen items to handle duplicates
        seen_instruments = {}  # instrument_name -> (rule, section_id)
        seen_sectors = {}  # sector_name -> (rule, section_id)
        seen_countries = {}  # country_name -> (rule, section_id)
        
        for section_idx, result in enumerate(section_results):
            if not isinstance(result, dict):
                logger.warning(f"⚠️ Section {section_idx+1} returned non-dict result: {type(result)}")
                continue
            
            # Process instrument rules
            for rule in result.get("instrument_rules", []):
                if not isinstance(rule, dict):
                    continue
                
                instrument = rule.get("instrument", "").strip().lower()
                if not instrument:
                    continue
                
                allowed = rule.get("allowed")
                reason = rule.get("reason", "")
                
                if instrument not in seen_instruments:
                    seen_instruments[instrument] = (rule, section_idx + 1)
                else:
                    # Handle duplicate - apply conflict resolution
                    existing_rule, existing_section = seen_instruments[instrument]
                    existing_allowed = existing_rule.get("allowed")
                    
                    # Prohibited overrides Allowed
                    if existing_allowed is True and allowed is False:
                        logger.debug(f"   🔄 Instrument '{rule.get('instrument')}': Section {existing_section} said allowed, Section {section_idx+1} said prohibited → keeping prohibited")
                        seen_instruments[instrument] = (rule, section_idx + 1)
                    elif existing_allowed is False and allowed is True:
                        logger.debug(f"   🔄 Instrument '{rule.get('instrument')}': Section {existing_section} said prohibited, Section {section_idx+1} said allowed → keeping prohibited")
                        # Keep existing (prohibited)
                    elif allowed == existing_allowed:
                        # Same status - keep the one with more detailed reason
                        if len(reason) > len(existing_rule.get("reason", "")):
                            seen_instruments[instrument] = (rule, section_idx + 1)
                            logger.debug(f"   🔄 Instrument '{rule.get('instrument')}': Same status, keeping more detailed reason from Section {section_idx+1}")
                    else:
                        # One is None/Review, keep the one with explicit status
                        if allowed is not None and existing_allowed is None:
                            seen_instruments[instrument] = (rule, section_idx + 1)
                        elif allowed is None and existing_allowed is not None:
                            pass  # Keep existing
                        else:
                            # Both None or both same - keep existing
                            pass
            
            # Process sector rules
            for rule in result.get("sector_rules", []):
                if not isinstance(rule, dict):
                    continue
                
                sector = rule.get("sector", "").strip().lower()
                if not sector:
                    continue
                
                allowed = rule.get("allowed")
                reason = rule.get("reason", "")
                
                if sector not in seen_sectors:
                    seen_sectors[sector] = (rule, section_idx + 1)
                else:
                    existing_rule, existing_section = seen_sectors[sector]
                    existing_allowed = existing_rule.get("allowed")
                    
                    if existing_allowed is True and allowed is False:
                        seen_sectors[sector] = (rule, section_idx + 1)
                    elif existing_allowed is False and allowed is True:
                        pass  # Keep existing (prohibited)
                    elif allowed == existing_allowed and len(reason) > len(existing_rule.get("reason", "")):
                        seen_sectors[sector] = (rule, section_idx + 1)
            
            # Process country rules
            for rule in result.get("country_rules", []):
                if not isinstance(rule, dict):
                    continue
                
                country = rule.get("country", "").strip().lower()
                if not country:
                    continue
                
                allowed = rule.get("allowed")
                reason = rule.get("reason", "")
                
                if country not in seen_countries:
                    seen_countries[country] = (rule, section_idx + 1)
                else:
                    existing_rule, existing_section = seen_countries[country]
                    existing_allowed = existing_rule.get("allowed")
                    
                    if existing_allowed is True and allowed is False:
                        seen_countries[country] = (rule, section_idx + 1)
                    elif existing_allowed is False and allowed is True:
                        pass  # Keep existing (prohibited)
                    elif allowed == existing_allowed and len(reason) > len(existing_rule.get("reason", "")):
                        seen_countries[country] = (rule, section_idx + 1)
            
            # Collect conflicts
            merged["conflicts"].extend(result.get("conflicts", []))
        
        # Convert seen dicts to lists
        merged["instrument_rules"] = [rule for rule, _ in seen_instruments.values()]
        merged["sector_rules"] = [rule for rule, _ in seen_sectors.values()]
        merged["country_rules"] = [rule for rule, _ in seen_countries.values()]
        
        logger.info(f"✅ Merged {len(section_results)} sections: {len(merged['instrument_rules'])} instruments, {len(merged['sector_rules'])} sectors, {len(merged['country_rules'])} countries")
        
        return merged
    
    def _create_empty_ocrd_json(self, fund_id: str) -> Dict[str, Any]:
        """Create empty OCRD data structure"""
        # OCRD schema with flat structure: future, option, and warrant are top-level sections (no parent "derivatives" category)
        OCRD_SCHEMA = {
            "bond": ["covered_bond", "asset_backed_security", "mortgage_bond", "pfandbrief", "public_mortgage_bond", "convertible_bond_regular", "convertible_bond_coco", "reverse_convertible", "credit_linked_note", "commercial_paper", "genussscheine_bondlike", "inflation_linked", "participation_paper", "plain_vanilla_bond", "promissory_note", "warrant_linked_bond"],
            "certificate": ["bond_certificate", "commodity_certificate", "currency_certificate", "fund_certificate", "index_certificate", "stock_certificate"],
            "stock": ["common_stock", "depositary_receipt", "genussschein_stocklike", "partizipationsschein", "preferred_stock", "reit", "right"],
            "fund": ["alternative_investment_fund", "commodity_fund", "equity_fund", "fixed_income_fund", "mixed_allocation_fund", "moneymarket_fund", "private_equity_fund", "real_estate_fund", "speciality_fund"],
            "deposit": ["call_money", "cash", "time_deposit"],
            "future": ["bond_future", "commodity_future", "currency_future", "fund_future", "index_future", "single_stock_future"],
            "option": ["bond_future_option", "commodity_future_option", "commodity_option", "currency_future_option", "currency_option", "fund_future_option", "fund_option", "index_future_option", "index_option", "stock_option"],
            "warrant": ["commodity_warrant", "currency_warrant", "fund_warrant", "index_warrant", "stock_warrant"],
            "commodity": ["precious_metal"],
            "forex": ["forex_outright", "forex_spot"],
            "swap": ["credit_default_swap", "interest_swap", "total_return_swap"],
            "loan": [],
            "private_equity": [],
            "real_estate": [],
            "rights": ["subscription_rights"]
        }
        
        out = {"fund_id": fund_id, "as_of": None, "sections": {}, "notes": []}
        # Note: allowed=None means not yet determined (will be set by rules)
        # allowed=True means explicitly allowed, allowed=False means explicitly prohibited
        # allowed=None can also mean manual approval required (set when mappings are ambiguous)
        # confidence: 0.0-1.0 score indicating match quality
        for section, rows in OCRD_SCHEMA.items():
            out["sections"][section] = {}
            for r in rows:
                out["sections"][section][r] = {"allowed": None, "confidence": None, "note": "", "evidence": {"page": None, "text": ""}}
            if section in ("stock", "fund", "bond", "certificate", "deposit", "commodity", "forex", "swap", "loan", "private_equity", "real_estate", "rights", "future", "option", "warrant"):
                out["sections"][section]["special_other_restrictions"] = []

        return out

    def _calculate_match_confidence(
        self, 
        excel_entry: Dict, 
        ocrd_key: str, 
        section_name: str,
        original_instrument: str
    ) -> float:
        """
        Calculate confidence score (0.0-1.0) for how well an Excel entry matches an OCRD instrument.
        
        Args:
            excel_entry: Excel mapping entry
            ocrd_key: OCRD instrument key (e.g., "common_stock")
            section_name: OCRD section name (e.g., "stock")
            original_instrument: Original instrument name from LLM rule
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        score = 0.0
        max_score = 0.0
        
        # Normalize strings for comparison
        instrument_category = excel_entry.get('instrument_category', '').lower()
        type2 = excel_entry.get('asset_tree_type2', '').lower().strip() if excel_entry.get('asset_tree_type2') else ''
        type3 = excel_entry.get('asset_tree_type3', '').lower().strip() if excel_entry.get('asset_tree_type3') else ''
        ocrd_key_normalized = ocrd_key.replace("_", " ").lower()
        original_normalized = original_instrument.lower()
        
        # 1. Exact match on type2 mapping (40 points)
        type2_to_key = {
            "plain vanilla bond": "plain_vanilla_bond",
            "covered bond": "covered_bond",
            "asset backed security": "asset_backed_security",
            "mortgage bond": "mortgage_bond",
            "pfandbrief": "pfandbrief",
            "public mortgage bond": "public_mortgage_bond",
            "convertible bond": "convertible_bond_regular",
            "commercial paper": "commercial_paper",
            "inflation linked": "inflation_linked",
            "promissory note": "promissory_note",
            "credit linked note": "credit_linked_note",
            "warrant linked bond": "warrant_linked_bond",
            "participation paper": "participation_paper",
            "reverse convertible": "reverse_convertible",
            "common stock": "common_stock",
            "preferred stock": "preferred_stock",
            "depositary receipt": "depositary_receipt",
            "right": "right",
            "partizipationsschein": "partizipationsschein",
            "reit": "reit",
            "equity fund": "equity_fund",
            "fixed income fund": "fixed_income_fund",
            "moneymarket fund": "moneymarket_fund",
            "real estate fund": "real_estate_fund",
            "real estate": "real_estate_fund",
            "alternative investment fund": "alternative_investment_fund",
            "private equity fund": "private_equity_fund",
            "cash": "cash",
            "call money": "call_money",
            "time deposit": "time_deposit",
            "bond future": "bond_future",
            "index future": "index_future",
            "currency future": "currency_future",
            "currency option": "currency_option",
            "index option": "index_option",
            "stock option": "stock_option",
            "forex outright": "forex_outright",
            "precious metal": "precious_metal",
        }
        
        if type2 and type2 in type2_to_key:
            if type2_to_key[type2] == ocrd_key:
                score += 40.0
        max_score += 40.0
        
        # 2. Type3 match (30 points)
        if type3 and type3 != 'nan':
            type3_parts = [p.strip().lower() for p in type3.split(',')]
            for part in type3_parts:
                if part in type2_to_key and type2_to_key[part] == ocrd_key:
                    score += 30.0
                    break
                # Fuzzy match on type3
                if part in ocrd_key_normalized or ocrd_key_normalized in part:
                    score += 20.0
                    break
        max_score += 30.0
        
        # 3. Instrument category contains OCRD key or vice versa (20 points)
        if ocrd_key_normalized in instrument_category or instrument_category in ocrd_key_normalized:
            score += 20.0
        elif any(word in ocrd_key_normalized for word in instrument_category.split() if len(word) > 3):
            score += 10.0
        max_score += 20.0
        
        # 4. Original instrument name match (10 points)
        if ocrd_key_normalized in original_normalized or original_normalized in ocrd_key_normalized:
            score += 10.0
        elif any(word in ocrd_key_normalized for word in original_normalized.split() if len(word) > 3):
            score += 5.0
        max_score += 10.0
        
        # Normalize to 0.0-1.0 range
        confidence = min(1.0, score / max_score) if max_score > 0 else 0.0
        
        return confidence
    
    def _normalize_instrument_name(self, name: str) -> str:
        """Normalize instrument names to improve matching accuracy."""
        if not name:
            return ""

        normalized = name.lower().strip()
        normalized = normalized.replace("-", " ")
        normalized = normalized.replace("_", " ")

        # Remove parenthetical text (e.g., "Interest rate futures (bond and money market)" -> "Interest rate futures")
        # This helps match instruments with descriptive text in parentheses
        normalized = re.sub(r"\([^)]*\)", "", normalized)

        # Treat FX as synonym for FOREX before matching
        normalized = re.sub(r"\bfx\b", "forex", normalized)
        normalized = re.sub(r"\bfx(?=\s)", "forex", normalized)
        normalized = re.sub(r"\bfx(?=[a-z])", "forex", normalized)

        # Normalize "foreign exchange" phrases to forex for consistency
        normalized = normalized.replace("foreign exchange", "forex")

        # Collapse multiple spaces
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized.strip()

    def _analyze_with_keywords(self, data: Dict[str, Any], text: str) -> Dict[str, Any]:
        """Fast keyword-based analysis"""
        text_lower = text.lower()
        
        # Define keywords for each instrument type
        instrument_keywords = {
            "bond": ["bond", "anleihe", "pfandbrief", "commercial paper", "inflation linked", "plain vanilla", "convertible", "covered bond", "asset backed", "mortgage bond"],
            "stock": ["stock", "aktie", "equity", "share", "common stock", "preferred stock", "reit", "depositary receipt", "genussschein", "partizipationsschein"],
            "fund": ["fund", "fonds", "equity fund", "fixed income fund", "money market fund", "mixed allocation fund", "alternative investment fund", "commodity fund", "private equity fund", "real estate fund"],
            "certificate": ["certificate", "zertifikat", "bond certificate", "commodity certificate", "currency certificate", "fund certificate", "index certificate", "stock certificate"],
            "future": ["future", "futures", "terminkontrakt", "bond future", "commodity future", "currency future", "index future"],
            "option": ["option", "options", "optionen", "bond option", "commodity option", "currency option", "stock option"],
            "warrant": ["warrant", "warrants", "optionsscheine", "scheine"],
            "deposit": ["deposit", "einlage", "call money", "cash", "time deposit"],
            "forex": ["forex", "foreign exchange", "currency", "währung", "devisen", "forex outright", "forex spot"]
        }
        
        # Define permission keywords
        permission_keywords = ["may invest", "allowed", "permitted", "authorized", "darf", "berechtigt", "erlaubt", "zugelassen", "investieren", "anlegen"]
        
        # Check if document allows investments
        has_permission = any(keyword in text_lower for keyword in permission_keywords)
        
        if has_permission:
            # Check each instrument type
            for instrument_type, keywords in instrument_keywords.items():
                # All sections are now flat (future, option, warrant are top-level)
                if instrument_type in data["sections"]:
                    # Handle both flat keywords (for non-derivative sections) and nested keywords (for derivative sections)
                    if isinstance(keywords, dict):
                        # Nested structure (old format) - handle each subtype separately
                        for subtype, subtype_keywords in keywords.items():
                            if subtype in data["sections"]:
                                found_keywords = [kw for kw in subtype_keywords if kw in text_lower]
                                if found_keywords:
                                    # Mark all items in this section as allowed
                                    for key in data["sections"][subtype]:
                                        if key != "special_other_restrictions":
                                            data["sections"][subtype][key]["allowed"] = True
                                            data["sections"][subtype][key]["note"] = f"Keyword analysis: Found {', '.join(found_keywords)}"
                                            data["sections"][subtype][key]["evidence"] = {
                                                "page": 1,
                                                "text": f"Document mentions: {', '.join(found_keywords)}"
                                            }
                    else:
                        # Flat structure (list of keywords)
                        found_keywords = [kw for kw in keywords if kw in text_lower]
                        
                        if found_keywords:
                            # Mark all items in this section as allowed
                            for key in data["sections"][instrument_type]:
                                if key != "special_other_restrictions":
                                    data["sections"][instrument_type][key]["allowed"] = True
                                    data["sections"][instrument_type][key]["note"] = f"Keyword analysis: Found {', '.join(found_keywords)}"
                                    data["sections"][instrument_type][key]["evidence"] = {
                                        "page": 1,
                                        "text": f"Document mentions: {', '.join(found_keywords)}"
                                    }
        
        return data
    
    async def _analyze_with_llm(self, data: Dict[str, Any], text: str, llm_provider: LLMProvider, model: str, trace_id: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """LLM-based analysis with section-based extraction - returns (structured_data, raw_analysis)"""
        try:
            # Check if LLM service is available
            if not self.llm_service:
                error_msg = "LLMService is not initialized. Cannot perform LLM analysis."
                logger.error(f"❌ {error_msg}")
                raise ValueError(error_msg)
            
            logger.info(f"🔍 Starting LLM analysis with {get_enum_value(llm_provider)}/{model}, text length: {len(text)}")
            
            # FIXED: Only use section-based extraction for large documents (>50k chars)
            # For smaller documents, process as single section to maintain backward compatibility
            USE_SECTION_BASED_EXTRACTION = len(text) > 50000
            
            # Add timeout wrapper to prevent hanging
            LLM_TIMEOUT = 300.0  # 5 minutes max per LLM call
            
            if not USE_SECTION_BASED_EXTRACTION:
                # Small document - process normally (backward compatible)
                logger.info("Processing document as single section (document size < 50k chars)")
                try:
                    analysis = await asyncio.wait_for(
                        self.llm_service.analyze_document(text, get_enum_value(llm_provider), model, trace_id),
                        timeout=LLM_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    logger.error(f"LLM analysis timed out after {LLM_TIMEOUT}s")
                    raise TimeoutError(f"Analysis timed out after {LLM_TIMEOUT} seconds. Document may be too large or API is slow.")
            else:
                # Large document - split into sections for better coverage
                logger.info(f"Large document detected ({len(text)} chars) - using section-based extraction")
                sections = self._split_document_into_sections(text)
                
                if len(sections) == 1:
                    # Even after splitting, only one section - process normally
                    logger.info("Processing document as single section")
                    try:
                        analysis = await asyncio.wait_for(
                            self.llm_service.analyze_document(text, get_enum_value(llm_provider), model, trace_id),
                            timeout=LLM_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"LLM analysis timed out after {LLM_TIMEOUT}s")
                        raise TimeoutError(f"Analysis timed out after {LLM_TIMEOUT} seconds. Document may be too large or API is slow.")
                else:
                    # Multiple sections - process each section separately with timeouts
                    logger.info(f"Processing {len(sections)} sections separately for better coverage")
                    section_results = []
                    
                    section_timeout = min(LLM_TIMEOUT, 120.0)  # 2 min per section max
                    
                    # Process sections sequentially (not concurrently) to save memory
                    # Process ALL sections, but in smaller batches to prevent memory exhaustion
                    logger.info(f"Processing all {len(sections)} sections sequentially...")
                    
                    for section_idx, section in enumerate(sections):
                        logger.info(f"Processing section {section_idx + 1}/{len(sections)}: '{section['title'][:50]}' ({len(section['text'])} chars)")
                        
                        # Process full section text - no truncation
                        section_text = section['text']
                        
                        try:
                            # Add timeout per section
                            section_analysis = await asyncio.wait_for(
                                self.llm_service.analyze_document(
                                    section_text, 
                                    get_enum_value(llm_provider), 
                                    model, 
                                    trace_id
                                ),
                                timeout=section_timeout
                            )
                            
                            if isinstance(section_analysis, dict):
                                instrument_count = len(section_analysis.get("instrument_rules", []))
                                logger.info(f"Section {section_idx + 1} found {instrument_count} instrument rules")
                                section_results.append(section_analysis)
                            else:
                                logger.warning(f"Section {section_idx + 1} returned non-dict result")
                                section_results.append({})
                        except asyncio.TimeoutError:
                            logger.error(f"Section {section_idx + 1} timed out after {section_timeout}s - skipping")
                            section_results.append({})  # Continue with other sections
                        except Exception as e:
                            logger.error(f"Error processing section {section_idx + 1}: {e}")
                            section_results.append({})  # Continue with other sections
                        
                        # Small delay between sections to prevent overwhelming the system
                        await asyncio.sleep(0.5)  # 500ms delay between sections
                    
                    # Merge results from all sections
                    logger.info(f"Merging results from {len(section_results)} sections...")
                    analysis = self._merge_section_results(section_results)
            
            # Log what LLM returned
            if isinstance(analysis, dict):
                instrument_count = len(analysis.get("instrument_rules", []))
                sector_count = len(analysis.get("sector_rules", []))
                country_count = len(analysis.get("country_rules", []))
                logger.info(f"📊 LLM returned: {instrument_count} instrument rules, {sector_count} sector rules, {country_count} country rules")
                
                if instrument_count > 0:
                    # Log first few instrument rules
                    for i, rule in enumerate(analysis.get("instrument_rules", [])[:3]):
                        allowed_val = rule.get("allowed") if isinstance(rule, dict) else getattr(rule, "allowed", None)
                        instrument_name = rule.get("instrument") if isinstance(rule, dict) else getattr(rule, "instrument", "unknown")
                        logger.info(f"  Instrument rule {i+1}: '{instrument_name}' = allowed={allowed_val}")
                else:
                    logger.warning("⚠️ LLM returned ZERO instrument rules! Attempting fallback with universal prompt...")
                    logger.warning("⚠️ This might indicate the document format doesn't match expected patterns (e.g., non-German format)")
                    
                    # Try fallback prompt (universal/language-agnostic)
                    try:
                        logger.info("🔄 Attempting fallback analysis with universal prompt...")
                        fallback_analysis = await asyncio.wait_for(
                            self.llm_service.analyze_document_fallback(text, get_enum_value(llm_provider), model, trace_id),
                            timeout=LLM_TIMEOUT
                        )
                        
                        fallback_instrument_count = len(fallback_analysis.get("instrument_rules", []))
                        if fallback_instrument_count > 0:
                            logger.info(f"✅ Fallback analysis successful! Found {fallback_instrument_count} instrument rules")
                            analysis = fallback_analysis  # Use fallback results
                            instrument_count = fallback_instrument_count
                            sector_count = len(analysis.get("sector_rules", []))
                            country_count = len(analysis.get("country_rules", []))
                            logger.info(f"📊 Fallback returned: {instrument_count} instrument rules, {sector_count} sector rules, {country_count} country rules")
                        else:
                            logger.warning("⚠️ Fallback analysis also returned ZERO instrument rules. Document may not contain investment rules.")
                    except asyncio.TimeoutError:
                        logger.error(f"Fallback analysis timed out after {LLM_TIMEOUT}s")
                        logger.warning("⚠️ Continuing with empty results from primary analysis")
                    except Exception as e:
                        logger.error(f"Fallback analysis failed: {e}", exc_info=True)
                        logger.warning("⚠️ Continuing with empty results from primary analysis")
            else:
                logger.error(f"❌ LLM returned non-dict response: {type(analysis)}")
                logger.error(f"❌ Response content: {str(analysis)[:500]}")
            
            # Validate analysis response
            if not isinstance(analysis, dict):
                logger.error(f"❌ Invalid analysis response format: {type(analysis)}")
                logger.error(f"❌ Response content: {str(analysis)[:500]}")
                raise Exception(f"Invalid analysis response format: {type(analysis)}")
            
            # Safety check: ensure we have at least an empty dict structure
            if not analysis.get("instrument_rules") and not analysis.get("sector_rules") and not analysis.get("country_rules"):
                logger.warning("⚠️ Analysis returned empty results - this might indicate an extraction issue")
                # Ensure at least empty lists exist
                if "instrument_rules" not in analysis:
                    analysis["instrument_rules"] = []
                if "sector_rules" not in analysis:
                    analysis["sector_rules"] = []
                if "country_rules" not in analysis:
                    analysis["country_rules"] = []
                if "conflicts" not in analysis:
                    analysis["conflicts"] = []
            
            # Convert LLM response using Excel mapping (includes negative logic detection)
            # Preserve original fund_id from data
            logger.info("🔄 Converting LLM response to OCRD format...")
            converted_data = self._convert_llm_response_to_ocrd_format(analysis, full_text=text)
            logger.info(f"✅ Conversion complete. Notes count: {len(converted_data.get('notes', []))}")
            # Merge with original data structure to preserve fund_id
            converted_data["fund_id"] = data.get("fund_id", "compliance_analysis")
            data = converted_data
            
            # Legacy code below - keeping for backward compatibility but not used if Excel mapping is active
            # Apply LLM results to data structure using helper function
            # self._apply_llm_decision(data, analysis, llm_provider, "bonds", list(data["sections"]["bond"].keys()))
            # self._apply_llm_decision(data, analysis, llm_provider, "stocks", list(data["sections"]["stock"].keys()))
            # self._apply_llm_decision(data, analysis, llm_provider, "funds", list(data["sections"]["fund"].keys()))
            
            # LEGACY CODE DISABLED: Derivatives are now handled via instrument_rules in _convert_llm_response_to_ocrd_format
            # This old code was setting derivatives to False when uncertain, which was overriding proper rule extraction
            # Derivatives should only be set based on explicit instrument rules from the document
            # try:
            #     derivatives_decision = analysis.get("derivatives", {}).get("allowed")
            #     evidence_text = analysis.get("derivatives", {}).get("evidence", "")
            #     
            #     if derivatives_decision == True:
            #         for subtype in ["future", "option", "warrant"]:
            #             if "derivative" in data["sections"] and subtype in data["sections"]["derivative"]:
            #                 for key in data["sections"]["derivative"][subtype]:
            #                     if key != "special_other_restrictions":
            #                         data["sections"]["derivative"][subtype][key]["allowed"] = True
            #                         data["sections"]["derivative"][subtype][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Derivatives allowed - {evidence_text}"
            #                         data["sections"]["derivative"][subtype][key]["evidence"] = {
            #                             "page": 1,
            #                             "text": evidence_text if evidence_text else "LLM analysis indicates derivatives are permitted"
            #                         }
            #     elif derivatives_decision == "Uncertain":
            #         # DISABLED: Don't set to False on uncertain - let instrument_rules handle it
            #         pass
            # except Exception as e:
            #     logger.error(f"Error processing derivatives: {e}", exc_info=True)
            #     # DISABLED: Don't set to False on error - let instrument_rules handle it
            #     pass
            
            return data, analysis
            
        except Exception as e:
            logger.error(f"LLM analysis error: {e}", exc_info=True)
            # Return data with error notes instead of failing completely
            for section_name in ["bond", "stock", "fund"]:
                if section_name in data["sections"]:
                    for key in data["sections"][section_name]:
                        if key != "special_other_restrictions":
                            data["sections"][section_name][key]["allowed"] = False
                            data["sections"][section_name][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Analysis error - {str(e)}"
                            data["sections"][section_name][key]["evidence"] = {
                                "page": 1,
                                "text": f"Analysis failed: {str(e)}"
                            }
            # LEGACY CODE DISABLED: Don't set derivatives to False on error
            # Derivatives should only be set based on explicit instrument rules from the document
            # if "derivative" in data["sections"]:
            #     for subtype in ["future", "option", "warrant"]:
            #         if subtype in data["sections"]["derivative"]:
            #             for key in data["sections"]["derivative"][subtype]:
            #                 if key != "special_other_restrictions":
            #                     data["sections"]["derivative"][subtype][key]["allowed"] = False
            #                     data["sections"]["derivative"][subtype][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Analysis error - {str(e)}"
            #                     data["sections"]["derivative"][subtype][key]["evidence"] = {
            #                         "page": 1,
            #                         "text": f"Analysis failed: {str(e)}"
            #                     }
            return data, {}
    
    async def _analyze_with_llm_traced(self, data: Dict[str, Any], text: str, llm_provider: LLMProvider, model: str, trace_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """LLM-based analysis with forensic tracing and section-based extraction - returns (structured_data, raw_analysis)"""
        try:
            # Check if LLM service is available
            if not self.llm_service:
                error_msg = "LLMService is not initialized. Cannot perform LLM analysis with tracing."
                logger.error(f"❌ {error_msg}")
                raise ValueError(error_msg)
            
            logger.info(f"🔍 Starting LLM analysis (TRACED) with {get_enum_value(llm_provider)}/{model}, text length: {len(text)}")
            
            # FIXED: Only use section-based extraction for large documents (>50k chars)
            # For smaller documents, process as single section to maintain backward compatibility
            USE_SECTION_BASED_EXTRACTION = len(text) > 50000
            
            if not USE_SECTION_BASED_EXTRACTION:
                # Small document - process normally (backward compatible)
                logger.info("📄 Processing document as single section (TRACED, document size < 50k chars)")
                analysis = await self.llm_service.analyze_document_with_tracing(text, get_enum_value(llm_provider), model, trace_id)
            else:
                # Large document - split into sections for better coverage
                logger.info(f"📑 Large document detected ({len(text)} chars) - using section-based extraction (TRACED)")
                sections = self._split_document_into_sections(text)
                
                if len(sections) == 1:
                    # Even after splitting, only one section - process normally
                    logger.info("📄 Processing document as single section (TRACED)")
                    analysis = await self.llm_service.analyze_document_with_tracing(text, get_enum_value(llm_provider), model, trace_id)
                else:
                    # Multiple sections - process each section separately
                    logger.info(f"📑 Processing {len(sections)} sections separately for better coverage (TRACED)")
                    section_results = []
                    
                    for section_idx, section in enumerate(sections):
                        logger.info(f"   🔍 Processing section {section_idx + 1}/{len(sections)}: '{section['title'][:50]}' ({len(section['text'])} chars)")
                        
                        try:
                            section_analysis = await self.llm_service.analyze_document_with_tracing(
                                section['text'], 
                                get_enum_value(llm_provider), 
                                model, 
                                trace_id
                            )
                            
                            if isinstance(section_analysis, dict):
                                instrument_count = len(section_analysis.get("instrument_rules", []))
                                logger.info(f"      ✅ Section {section_idx + 1} found {instrument_count} instrument rules")
                                section_results.append(section_analysis)
                            else:
                                logger.warning(f"      ⚠️ Section {section_idx + 1} returned non-dict result")
                                section_results.append({})
                        except Exception as e:
                            logger.error(f"      ❌ Error processing section {section_idx + 1}: {e}", exc_info=True)
                            section_results.append({})  # Continue with other sections
                    
                    # Merge results from all sections
                    logger.info(f"🔄 Merging results from {len(section_results)} sections...")
                    analysis = self._merge_section_results(section_results)
            
            # Log what LLM returned
            if isinstance(analysis, dict):
                instrument_count = len(analysis.get("instrument_rules", []))
                sector_count = len(analysis.get("sector_rules", []))
                country_count = len(analysis.get("country_rules", []))
                logger.info(f"📊 LLM returned (TRACED): {instrument_count} instrument rules, {sector_count} sector rules, {country_count} country rules")
                
                if instrument_count > 0:
                    # Log first few instrument rules
                    for i, rule in enumerate(analysis.get("instrument_rules", [])[:3]):
                        allowed_val = rule.get("allowed") if isinstance(rule, dict) else getattr(rule, "allowed", None)
                        instrument_name = rule.get("instrument") if isinstance(rule, dict) else getattr(rule, "instrument", "unknown")
                        logger.info(f"  Instrument rule {i+1}: '{instrument_name}' = allowed={allowed_val}")
                else:
                    logger.warning("⚠️ LLM returned ZERO instrument rules (TRACED)! Attempting fallback with universal prompt...")
                    logger.warning("⚠️ This might indicate the document format doesn't match expected patterns (e.g., non-German format)")
                    
                    # Try fallback prompt (universal/language-agnostic)
                    try:
                        logger.info("🔄 Attempting fallback analysis with universal prompt (TRACED)...")
                        LLM_TIMEOUT = 300.0
                        fallback_analysis = await asyncio.wait_for(
                            self.llm_service.analyze_document_fallback(text, get_enum_value(llm_provider), model, trace_id),
                            timeout=LLM_TIMEOUT
                        )
                        
                        fallback_instrument_count = len(fallback_analysis.get("instrument_rules", []))
                        if fallback_instrument_count > 0:
                            logger.info(f"✅ Fallback analysis successful (TRACED)! Found {fallback_instrument_count} instrument rules")
                            analysis = fallback_analysis  # Use fallback results
                            instrument_count = fallback_instrument_count
                            sector_count = len(analysis.get("sector_rules", []))
                            country_count = len(analysis.get("country_rules", []))
                            logger.info(f"📊 Fallback returned (TRACED): {instrument_count} instrument rules, {sector_count} sector rules, {country_count} country rules")
                        else:
                            logger.warning("⚠️ Fallback analysis also returned ZERO instrument rules (TRACED). Document may not contain investment rules.")
                    except asyncio.TimeoutError:
                        logger.error(f"Fallback analysis timed out after {LLM_TIMEOUT}s (TRACED)")
                        logger.warning("⚠️ Continuing with empty results from primary analysis")
                    except Exception as e:
                        logger.error(f"Fallback analysis failed (TRACED): {e}", exc_info=True)
                        logger.warning("⚠️ Continuing with empty results from primary analysis")
            
            # Validate analysis response
            if not isinstance(analysis, dict):
                raise Exception(f"Invalid analysis response format: {type(analysis)}")
            
            # Convert LLM response using Excel mapping (includes negative logic detection)
            # This is the SAME conversion method used in _analyze_with_llm
            logger.info("🔄 Converting LLM response to OCRD format (TRACED)...")
            converted_data = self._convert_llm_response_to_ocrd_format(analysis, full_text=text)
            logger.info(f"✅ Conversion complete (TRACED). Notes count: {len(converted_data.get('notes', []))}")
            
            # Merge with original data structure to preserve fund_id
            converted_data["fund_id"] = data.get("fund_id", "compliance_analysis")
            data = converted_data
            
            # Legacy code below - keeping for backward compatibility but not used if Excel mapping is active
            # Apply LLM results to data structure using helper function
            # self._apply_llm_decision(data, analysis, llm_provider, "bonds", list(data["sections"]["bond"].keys()))
            # self._apply_llm_decision(data, analysis, llm_provider, "stocks", list(data["sections"]["stock"].keys()))
            # self._apply_llm_decision(data, analysis, llm_provider, "funds", list(data["sections"]["fund"].keys()))
            
            # LEGACY CODE DISABLED: Derivatives are now handled via instrument_rules in _convert_llm_response_to_ocrd_format
            # This old code was setting derivatives to False when uncertain, which was overriding proper rule extraction
            # Derivatives should only be set based on explicit instrument rules from the document
            # derivatives_decision = analysis.get("derivatives", {}).get("allowed")
            # evidence_text = analysis.get("derivatives", {}).get("evidence", "")
            # 
            # if derivatives_decision == True:
            #     for subtype in ["future", "option", "warrant"]:
            #         if "derivative" in data["sections"] and subtype in data["sections"]["derivative"]:
            #             for key in data["sections"]["derivative"][subtype]:
            #                 if key != "special_other_restrictions":
            #                     data["sections"]["derivative"][subtype][key]["allowed"] = True
            #                     data["sections"]["derivative"][subtype][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Derivatives allowed - {evidence_text}"
            #                     data["sections"]["derivative"][subtype][key]["evidence"] = {
            #                         "page": 1,
            #                         "text": evidence_text if evidence_text else "LLM analysis indicates derivatives are permitted"
            #                     }
            # elif derivatives_decision == "Uncertain":
            #     # DISABLED: Don't set to False on uncertain - let instrument_rules handle it
            #     pass
            
            return data, analysis
            
        except Exception as e:
            raise Exception(f"LLM analysis failed: {str(e)}")
    
    def _apply_llm_decision(self, data: Dict[str, Any], analysis: Dict, llm_provider: LLMProvider, 
                           investment_type: str, section_keys: list) -> None:
        """Apply LLM decision to data structure, handling Uncertain responses"""
        try:
            # Map plural investment types to singular section names
            section_mapping = {
                "bonds": "bond",
                "stocks": "stock", 
                "funds": "fund",
                "derivatives": "future"  # Map derivatives to future section
            }
            
            section_name = section_mapping.get(investment_type, investment_type)
            
            decision = analysis.get(investment_type, {}).get("allowed")
            evidence_text = analysis.get(investment_type, {}).get("evidence", "")
            
            if decision == True:
                for key in section_keys:
                    if key != "special_other_restrictions":
                        data["sections"][section_name][key]["allowed"] = True
                        data["sections"][section_name][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): {investment_type.title()} allowed - {evidence_text}"
                        data["sections"][section_name][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else f"LLM analysis indicates {investment_type} are permitted"
                        }
            elif decision == "Uncertain":
                for key in section_keys:
                    if key != "special_other_restrictions":
                        data["sections"][section_name][key]["allowed"] = False
                        data["sections"][section_name][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): {investment_type.title()} uncertain - {evidence_text}"
                        data["sections"][section_name][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "Uncertain - no explicit statement found"
                        }
            # If decision is False or any other value, leave as default (False)
        except Exception as e:
            logger.error(f"Error applying LLM decision for {investment_type}: {e}", exc_info=True)
            # Set all items to uncertain on error
            for key in section_keys:
                if key != "special_other_restrictions":
                    data["sections"][section_name][key]["allowed"] = False
                    data["sections"][section_name][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): {investment_type.title()} error - {str(e)}"
                    data["sections"][section_name][key]["evidence"] = {
                        "page": 1,
                        "text": f"Error processing {investment_type}: {str(e)}"
                    }

    def _validate_llm_response(self, llm_response: Dict[str, Any]) -> LLMResponse:
        """Validate LLM response using Pydantic models"""
        # Check for errors first
        if "error" in llm_response:
            raise ValueError(f"LLM failed: {llm_response['error']}")
        
        # Use Pydantic for automatic validation
        try:
            validated_response = LLMResponse.from_dict(llm_response)
            logger.debug(f"✅ LLM response validated successfully with Pydantic")
            return validated_response
        except Exception as e:
            # Provide helpful error message
            error_msg = str(e)
            logger.error(f"❌ LLM response validation failed: {error_msg}")
            raise ValueError(f"Invalid LLM response structure: {error_msg}")
    
    def _convert_llm_response_to_ocrd_format(self, llm_response: Dict[str, Any], full_text: Optional[str] = None) -> Dict[str, Any]:
        """Convert LLM response to OCRD format for Excel export"""
        # DIAGNOSTIC: Log raw LLM response for derivatives debugging
        instrument_rules = llm_response.get("instrument_rules", [])
        derivatives_rules = [
            r for r in instrument_rules
            if any(term in str(r.get("instrument", "") if isinstance(r, dict) else getattr(r, "instrument", "")).lower()
                   for term in ["derivative", "future", "option", "warrant"])
        ]
        if derivatives_rules:
            logger.info("🔍 [DIAGNOSTIC] Raw LLM derivatives rules:")
            for rule in derivatives_rules:
                if isinstance(rule, dict):
                    logger.info(f"  - {rule.get('instrument')}: allowed={rule.get('allowed')}, reason='{rule.get('reason', '')[:100]}...'")
                else:
                    logger.info(f"  - {getattr(rule, 'instrument', 'unknown')}: allowed={getattr(rule, 'allowed', None)}, reason='{getattr(rule, 'reason', '')[:100]}...'")
        else:
            logger.warning("⚠️ [DIAGNOSTIC] No derivatives rules found in raw LLM response")
        
        # Validate using Pydantic (returns LLMResponse object)
        validated_response = self._validate_llm_response(llm_response)
        
        # Use validated response for type-safe access
        sector_count = len(validated_response.sector_rules)
        country_count = len(validated_response.country_rules)
        instrument_count = len(validated_response.instrument_rules)
        
        logger.info(f"📊 LLM Response validated: sector_rules={sector_count}, "
              f"country_rules={country_count}, "
              f"instrument_rules={instrument_count}")
        
        if instrument_count > 0:
            logger.info("📋 First 3 instrument rules from LLM:")
            for i, rule in enumerate(validated_response.instrument_rules[:3]):
                logger.info(f"  [{i+1}] instrument='{rule.instrument}', allowed={rule.allowed}, reason='{rule.reason[:80]}...'")
        else:
            logger.warning("⚠️ instrument_rules is EMPTY! LLM didn't extract any instrument rules.")
        
        # Use validated response for type-safe access
        sector_count = len(validated_response.sector_rules)
        country_count = len(validated_response.country_rules)
        instrument_count = len(validated_response.instrument_rules)
        
        # Create empty OCRD structure
        data = {"fund_id": "compliance_analysis", "as_of": None, "sections": {}, "notes": []}
        
        # Add debug info to notes so it's visible in results
        debug_info = f"[DEBUG] LLM returned: {sector_count} sector rules, {country_count} country rules, {instrument_count} instrument rules"
        data["notes"].append(debug_info)
        logger.debug(debug_info)
        
        # Log actual instrument rules if any (using validated response)
        if instrument_count > 0:
            logger.info("📋 Processing instrument rules details:")
            for i, rule in enumerate(validated_response.instrument_rules[:5]):
                logger.info(f"  [{i+1}] instrument='{rule.instrument}', allowed={rule.allowed}, reason='{rule.reason[:100]}...'")
                data["notes"].append(
                    f"[DEBUG] Rule {i+1}: '{rule.instrument}' = {rule.allowed}"
                )
        
        # OCRD schema
        # Note: future, option, and warrant are now top-level sections (no parent "derivatives" category)
        OCRD_SCHEMA = {
            "bond": ["covered_bond", "asset_backed_security", "mortgage_bond", "pfandbrief", "public_mortgage_bond", "convertible_bond_regular", "convertible_bond_coco", "reverse_convertible", "credit_linked_note", "commercial_paper", "genussscheine_bondlike", "inflation_linked", "participation_paper", "plain_vanilla_bond", "promissory_note", "warrant_linked_bond"],
            "certificate": ["bond_certificate", "commodity_certificate", "currency_certificate", "fund_certificate", "index_certificate", "stock_certificate"],
            "stock": ["common_stock", "depositary_receipt", "genussschein_stocklike", "partizipationsschein", "preferred_stock", "reit", "right"],
            "fund": ["alternative_investment_fund", "commodity_fund", "equity_fund", "fixed_income_fund", "mixed_allocation_fund", "moneymarket_fund", "private_equity_fund", "real_estate_fund", "speciality_fund"],
            "deposit": ["call_money", "cash", "time_deposit"],
            "future": ["bond_future", "commodity_future", "currency_future", "fund_future", "index_future", "single_stock_future"],
            "option": ["bond_future_option", "commodity_future_option", "commodity_option", "currency_future_option", "currency_option", "fund_future_option", "fund_option", "index_future_option", "index_option", "stock_option"],
            "warrant": ["commodity_warrant", "currency_warrant", "fund_warrant", "index_warrant", "stock_warrant"],
            "commodity": ["precious_metal"],
            "forex": ["forex_outright", "forex_spot"],
            "swap": ["credit_default_swap", "interest_swap", "total_return_swap"],
            "loan": [],
            "private_equity": [],
            "real_estate": [],
            "rights": ["subscription_rights"]
        }
        
        # Initialize sections
        # Note: allowed=None means not yet determined (will be set by rules)
        # allowed=True means explicitly allowed, allowed=False means explicitly prohibited
        # allowed=None can also mean manual approval required (set when mappings are ambiguous)
        # Initialize all sections as flat structures (future, option, warrant are now top-level)
        for section, rows in OCRD_SCHEMA.items():
            data["sections"][section] = {}
            for r in rows:
                data["sections"][section][r] = {"allowed": None, "confidence": None, "note": "", "evidence": {"page": None, "text": ""}}
            if section in ("stock", "fund", "bond", "certificate", "deposit", "commodity", "forex", "swap", "loan", "private_equity", "real_estate", "rights", "future", "option", "warrant"):
                data["sections"][section]["special_other_restrictions"] = []
        
        # Apply sector rules (using validated response)
        for rule in validated_response.sector_rules:
            sector = rule.sector.lower()
            allowed = rule.allowed
            reason = rule.reason
            
            # Map sectors to relevant instrument types
            sector_mapping = {
                "energy": ["bond", "stock", "fund"],
                "healthcare": ["bond", "stock", "fund"],
                "defense": ["bond", "stock", "fund"],
                "tobacco": ["bond", "stock", "fund"],
                "gambling": ["bond", "stock", "fund"],
                "weapons": ["bond", "stock", "fund"]
            }
            
            affected_sections = sector_mapping.get(sector, ["bond", "stock", "fund"])
            for section in affected_sections:
                if section in data["sections"]:
                    for key in data["sections"][section]:
                        if key != "special_other_restrictions":
                            data["sections"][section][key]["allowed"] = allowed
                            data["sections"][section][key]["note"] = f"Sector rule: {sector} - {reason}"
                            data["sections"][section][key]["evidence"] = {
                                "page": 1,
                                "text": reason
                            }
        
        # Apply country rules (using validated response)
        for rule in validated_response.country_rules:
            country = rule.country
            allowed = rule.allowed
            reason = rule.reason
            
            # Add to notes
            data["notes"].append(f"Country rule: {country} - {'Allowed' if allowed else 'Prohibited'} - {reason}")
        
        # Apply instrument rules using Excel mapping if available (using validated response)
        processed_instruments = set()  # Track which instruments we've processed
        instrument_rules = validated_response.instrument_rules
        
        if not instrument_rules:
            logger.warning("⚠️ No instrument_rules extracted from LLM! This is why allowed_count is 0.")
            logger.warning("⚠️ Check if LLM is returning instrument_rules in the response")
            data["notes"].append("[WARNING] No instrument rules extracted from PDF. LLM may not have found any investment instruments mentioned.")
            # CRITICAL: Do NOT set derivatives to False when no rules are found - they should remain None
            logger.info("ℹ️ No instrument rules found - derivatives will remain as None (not determined) until explicit rules are found")
        else:
            logger.info(f"✅ Processing {len(instrument_rules)} instrument rules from LLM")
            allowed_count_in_rules = sum(1 for r in instrument_rules if r.allowed is True)
            prohibited_count_in_rules = sum(1 for r in instrument_rules if r.allowed is False)
            logger.info(f"✅ {allowed_count_in_rules}/{len(instrument_rules)} rules have allowed=True, {prohibited_count_in_rules} have allowed=False")
            # Log first few rules for debugging
            for i, rule in enumerate(instrument_rules[:5]):
                logger.info(f"  Rule {i+1}: '{rule.instrument}' = allowed={rule.allowed}, reason='{rule.reason[:80]}...'")
        
        for rule in instrument_rules:
            original_instrument = rule.instrument.strip()
            instrument_lower = original_instrument.lower()
            instrument_normalized = self._normalize_instrument_name(original_instrument)
            allowed = rule.allowed
            reason = rule.reason

            # CRITICAL VALIDATION: Reject rules that mark instruments as prohibited without proper evidence
            # BUT: Parent "Derivatives" category doesn't require its own evidence - it derives from children
            is_derivatives_parent = instrument_lower in ["derivatives", "derivate", "derivative"]
            is_derivative_subtype = any(term in instrument_lower for term in ["future", "option", "warrant"])
            
            # RELAXED: Only validate subtypes, not the parent "Derivatives" category
            # Relaxed rules: Accept derivative prohibitions with minimal evidence (reduced from strict validation)
            if allowed is False and is_derivative_subtype and not is_derivatives_parent:
                # Relaxed: Accept if there's ANY reason text (reduced from requiring explicit prohibition language)
                if not reason or len(reason.strip()) < 5:  # Reduced from 10 to 5 characters
                    logger.info(
                        f"ℹ️ RELAXED: Accepting derivative prohibition for '{original_instrument}' with minimal evidence. "
                        f"Reason: '{reason[:100] if reason else 'N/A'}...'"
                    )
                    # Continue processing instead of rejecting
                else:
                    logger.info(
                        f"ℹ️ Accepting derivative prohibition for '{original_instrument}' with evidence: '{reason[:100]}...'"
                    )
            
            # CRITICAL: Strict validation for derivative subtypes - require strong evidence for allowances
            # Conservative approach: Derivatives default to NOT ALLOWED unless explicitly and clearly allowed
            if is_derivative_subtype and allowed is False:
                # Prohibitions are fine - accept with minimal evidence (conservative)
                if not reason or len(reason.strip()) < 5:
                    logger.info(
                        f"ℹ️ Accepting derivative prohibition for '{original_instrument}' with minimal evidence. "
                        f"Keeping allowed=False. Reason: '{reason[:100] if reason else 'N/A'}...'"
                    )
                    # Keep allowed=False - prohibitions are conservative
                else:
                    logger.info(
                        f"ℹ️ Accepting derivative prohibition for '{original_instrument}' with evidence: '{reason[:100]}...'"
                    )
                    # Keep allowed=False
            elif is_derivative_subtype and allowed is True:
                # STRICT: Require strong evidence for derivative allowances (conservative approach)
                # Minimum 20 characters of evidence text required
                if not reason or len(reason.strip()) < 20:
                    logger.warning(
                        f"⚠️ CONSERVATIVE: Rejecting derivative allowance for '{original_instrument}' - insufficient evidence. "
                        f"Requires at least 20 characters of evidence text. "
                        f"Current reason: '{reason[:100] if reason else 'N/A'}...' "
                        f"Setting to NOT ALLOWED (conservative default)."
                    )
                    # Reject the allowance - set to False (conservative default)
                    allowed = False
                    reason = f"Insufficient evidence for allowance. Original reason: {reason if reason else 'No reason provided'}"
                    logger.info(
                        f"🔄 Changed '{original_instrument}' from allowed=True to allowed=False due to insufficient evidence"
                    )
                else:
                    # Check for explicit allowance language
                    reason_lower = reason.lower()
                    explicit_allowance_indicators = [
                        "allowed", "permitted", "authorized", "zulässig", "erlaubt", 
                        "zugelassen", "ja", "yes", "x", "✓", "check"
                    ]
                    has_explicit_allowance = any(indicator in reason_lower for indicator in explicit_allowance_indicators)
                    
                    if not has_explicit_allowance:
                        logger.warning(
                            f"⚠️ CONSERVATIVE: Derivative allowance for '{original_instrument}' lacks explicit allowance language. "
                            f"Evidence: '{reason[:100]}...' Setting to NOT ALLOWED (conservative default)."
                        )
                        allowed = False
                        reason = f"No explicit allowance language found. Original reason: {reason}"
                        logger.info(
                            f"🔄 Changed '{original_instrument}' from allowed=True to allowed=False - no explicit allowance language"
                        )
                    else:
                        logger.info(
                            f"✅ Accepting derivative allowance for '{original_instrument}' with sufficient evidence: '{reason[:100]}...'"
                        )
            
            # Skip parent "Derivatives" category rules - no parent category exists anymore
            # Future, option, and warrant are now top-level sections
            if is_derivatives_parent:
                logger.info(
                    f"⚠️ SKIPPING 'Derivatives' rule - no parent category exists. "
                    f"Future, option, and warrant are now top-level sections. "
                    f"LLM extracted: allowed={allowed}, but this will be ignored."
                )
                continue  # Skip this rule entirely - don't process it

            logger.info(
                f"🔍 Processing rule: instrument='{original_instrument}', "
                f"normalized='{instrument_normalized}', allowed={allowed}, "
                f"reason='{reason[:100]}...'"
            )

            # Check for negative logic if Excel mapping is available
            excel_mapping_succeeded = False  # Track if Excel mapping actually updated OCRD structure
            if self.excel_mapping:
                # Use Excel mapping to find matching entries
                # Use full text context if available for better negative logic detection
                context_for_matching = full_text if full_text else reason
                matching_entries = []

                # Try multiple search variants to maximize matches (exact, normalized, underscore)
                search_variants = {
                    instrument_lower,
                    instrument_lower.replace(" ", "_"),
                    instrument_normalized,
                    instrument_normalized.replace(" ", "_")
                }

                for search_term in search_variants:
                    if not search_term:
                        continue
                    matching_entries = self.excel_mapping.find_matching_entries(
                        search_term,
                        context=context_for_matching
                    )
                    if matching_entries:
                        break

                # Only log if Excel mapping has data (to reduce noise when Excel mapping is empty)
                if hasattr(self.excel_mapping, 'instrument_lookup') and len(self.excel_mapping.instrument_lookup) > 0:
                    logger.info(
                        f"🔍 Excel mapping for '{instrument_normalized}': "
                        f"found {len(matching_entries)} entries"
                    )
                    if matching_entries:
                        for i, entry in enumerate(matching_entries[:3]):
                            logger.info(f"  Match {i+1}: '{entry.get('instrument_category', 'unknown')}' → Type1={entry.get('asset_tree_type1')}, Type2={entry.get('asset_tree_type2')}")
                    else:
                        # Log at info level when Excel mapping has data but no match found
                        logger.info(f"⚠️ No matches found for '{instrument_normalized}' in Excel mapping")
                else:
                    # Excel mapping is empty - don't log warnings, just skip silently
                    logger.debug(f"Excel mapping is empty - skipping match attempt for '{instrument_normalized}'")
                
                # Only check negative logic if we have matching entries (more reliable)
                if matching_entries:
                    # CRITICAL: Do NOT flip logic if reason explicitly mentions "Zulässige Anlagen" (Permitted Investments)
                    reason_lower = reason.lower() if reason else ""
                    is_zulaessige_anlagen = any(phrase in reason_lower for phrase in [
                        "zulässige anlagen", "zulässige anlageinstrumente", 
                        "listed in zulässige", "permitted investments"
                    ])
                    
                    # CRITICAL: Do NOT flip logic if reason explicitly mentions "Unzulässige Anlagen" (Prohibited Investments)
                    is_unzulaessige_anlagen = any(phrase in reason_lower for phrase in [
                        "unzulässige anlagen", "unzulässige anlageinstrumente",
                        "listed in unzulässige", "prohibited investments"
                    ])
                    
                    if is_zulaessige_anlagen:
                        # Item is explicitly in permitted section - ensure it's allowed=True
                        if not allowed:
                            logger.warning(
                                f"⚠️ EXCEL MAPPING: Item '{original_instrument}' is in Zulässige Anlagen but allowed=False. "
                                f"Setting to allowed=True to match section context."
                            )
                            allowed = True
                        logger.info(
                            f"✅ EXCEL MAPPING: Item '{original_instrument}' confirmed in Zulässige Anlagen section - keeping allowed=True"
                        )
                    elif is_unzulaessige_anlagen:
                        # Item is explicitly in prohibited section - ensure it's allowed=False
                        if allowed:
                            logger.warning(
                                f"⚠️ EXCEL MAPPING: Item '{original_instrument}' is in Unzulässige Anlagen but allowed=True. "
                                f"Setting to allowed=False to match section context."
                            )
                            allowed = False
                        logger.info(
                            f"✅ EXCEL MAPPING: Item '{original_instrument}' confirmed in Unzulässige Anlagen section - keeping allowed=False"
                        )
                    else:
                        # Check for negative logic in the full text context (better detection)
                        is_negative, neg_explanation = self.excel_mapping.detect_negative_logic(
                            context_for_matching,
                            original_instrument
                        )
                        if is_negative:
                            allowed = not allowed  # Flip the logic
                            reason = f"{reason} [Negative logic detected: {neg_explanation}]"
                            logger.info(
                                f"EXCEL MAPPING: Negative logic detected for '{original_instrument}': {neg_explanation}"
                            )
                
                # Update Excel mapping entries AND populate OCRD structure using Asset Tree
                for entry in matching_entries:
                    self.excel_mapping.update_allowed_status(entry['row_id'], allowed, reason)
                    logger.debug(f"EXCEL MAPPING: Updated entry '{entry['instrument_category']}' (row {entry['row_id']}) to allowed={allowed}")
                    
                    # Use Asset Tree to populate OCRD structure directly
                    # Raw values from Excel
                    raw_type1 = entry.get('asset_tree_type1', '')
                    raw_type2 = entry.get('asset_tree_type2', '')
                    raw_type3 = entry.get('asset_tree_type3', '')
                    
                    # Normalize and handle multi-valued type1 like "future, option, warrant"
                    type1_candidates = []
                    if raw_type1:
                        # Split on comma / slash / semicolon
                        for part in re.split(r'[,/;]', str(raw_type1)):
                            p = part.strip().lower()
                            if p and p != 'nan':
                                type1_candidates.append(p)
                    
                    # Pick the first type1 that actually exists in OCRD sections
                    type1 = None
                    for cand in type1_candidates or [str(raw_type1).lower().strip()]:
                        if cand in data["sections"]:
                            type1 = cand
                            break
                    
                    # Normal type2/type3 normalization
                    type2 = str(raw_type2).lower().strip() if raw_type2 and str(raw_type2).lower().strip() != 'nan' else None
                    type3 = str(raw_type3).lower().strip() if raw_type3 and str(raw_type3).lower().strip() != 'nan' else None
                    
                    if type1 and type1 in data["sections"]:
                        # Map type2 to specific instrument names in OCRD schema
                        # This mapping is generated from Investment_Mapping.xlsx
                        type2_to_key = {
                            # Bonds
                            "plain vanilla bond": "plain_vanilla_bond",
                            "covered bond": "covered_bond",
                            "asset backed security": "asset_backed_security",
                            "mortgage bond": "mortgage_bond",
                            "pfandbrief": "pfandbrief",
                            "public mortgage bond": "public_mortgage_bond",
                            "convertible bond": "convertible_bond_regular",
                            "commercial paper": "commercial_paper",
                            "inflation linked": "inflation_linked",
                            "promissory note": "promissory_note",
                            "credit linked note": "credit_linked_note",
                            "warrant linked bond": "warrant_linked_bond",
                            "participation paper": "participation_paper",
                            "reverse convertible": "reverse_convertible",
                            # Stocks
                            "common stock": "common_stock",
                            "preferred stock": "preferred_stock",
                            "depositary receipt": "depositary_receipt",
                            "right": "right",
                            "partizipationsschein": "partizipationsschein",
                            "reit": "reit",
                            # Funds
                            "equity fund": "equity_fund",
                            "fixed income fund": "fixed_income_fund",
                            "moneymarket fund": "moneymarket_fund",
                            "real estate fund": "real_estate_fund",
                            "real estate": "real_estate_fund",
                            "alternative investment fund": "alternative_investment_fund",
                            "private equity fund": "private_equity_fund",
                            # Deposits
                            "cash": "cash",
                            "call money": "call_money",
                            "time deposit": "time_deposit",
                            # Futures
                            "bond future": "bond_future",
                            "index future": "index_future",
                            "currency future": "currency_future",
                            "equity future": "single_stock_future",
                            "equity futures": "single_stock_future",
                            "single stock future": "single_stock_future",
                            "equity index future": "index_future",
                            "equity index futures": "index_future",
                            "aktienfutures": "single_stock_future",
                            "aktienindexfutures": "index_future",
                            # Options
                            "currency option": "currency_option",
                            "index option": "index_option",
                            "stock option": "stock_option",
                            "equity option": "stock_option",
                            "equity options": "stock_option",
                            "equity index option": "index_option",
                            "equity index options": "index_option",
                            "aktienoptionen": "stock_option",
                            "aktienindexoptionen": "index_option",
                            # Forex
                            "forex outright": "forex_outright",
                            # Commodities
                            "precious metal": "precious_metal",
                        }
                        
                        # Try to find matching key in section with confidence scoring
                        section = data["sections"][type1]
                        candidate_matches = []  # List of (key, confidence_score) tuples
                        
                        # First try type2 mapping
                        if type2 and type2 in type2_to_key:
                            key = type2_to_key[type2]
                            if key in section:
                                confidence = self._calculate_match_confidence(entry, key, type1, original_instrument)
                                candidate_matches.append((key, confidence))
                        
                        # Handle Type3 - can contain multiple comma-separated instrument names
                        if type3 and type3 != 'nan':
                            type3_parts = [p.strip().lower() for p in type3.split(',')]
                            for part in type3_parts:
                                # Try direct mapping first
                                if part in type2_to_key:
                                    key = type2_to_key[part]
                                    if key in section:
                                        confidence = self._calculate_match_confidence(entry, key, type1, original_instrument)
                                        # Only add if not already added or with higher confidence
                                        existing = next(((k, c) for k, c in candidate_matches if k == key), None)
                                        if not existing or confidence > existing[1]:
                                            if existing:
                                                candidate_matches.remove(existing)
                                            candidate_matches.append((key, confidence))
                                else:
                                    # Try fuzzy matching
                                    for key in section.keys():
                                        if key != "special_other_restrictions":
                                            key_normalized = key.replace("_", " ").lower()
                                            if part in key_normalized or key_normalized in part:
                                                confidence = self._calculate_match_confidence(entry, key, type1, original_instrument)
                                                existing = next(((k, c) for k, c in candidate_matches if k == key), None)
                                                if not existing or confidence > existing[1]:
                                                    if existing:
                                                        candidate_matches.remove(existing)
                                                    candidate_matches.append((key, confidence))
                                                break
                        
                        # If no match from type2/type3, try fuzzy matching on type2
                        if not candidate_matches and type2:
                            for key in section.keys():
                                if key != "special_other_restrictions":
                                    key_normalized = key.replace("_", " ").lower()
                                    if type2 in key_normalized or key_normalized in type2:
                                        confidence = self._calculate_match_confidence(entry, key, type1, original_instrument)
                                        candidate_matches.append((key, confidence))
                                        break
                        
                        # If still no matches, try all keys in section with confidence scoring
                        if not candidate_matches:
                            for key in section.keys():
                                if key != "special_other_restrictions":
                                    confidence = self._calculate_match_confidence(entry, key, type1, original_instrument)
                                    if confidence > 0.0:  # Only consider matches with some confidence
                                        candidate_matches.append((key, confidence))
                        
                        # Sort by confidence (highest first)
                        candidate_matches.sort(key=lambda x: x[1], reverse=True)
                        
                        # Apply to matched keys based on confidence
                        # Be more permissive: if there is exactly ONE candidate, auto-approve it
                        CONFIDENCE_THRESHOLD = 0.5  # was 0.7, slightly lower for practical use
                        HIGH_CONFIDENCE_DIFF = 0.15  # 15% difference to prefer one match over others
                        
                        if candidate_matches:
                            best_match = candidate_matches[0]
                            best_key, best_confidence = best_match
                            
                            # NEW: if we have exactly one candidate, treat it as a clear winner
                            has_clear_winner = (
                                len(candidate_matches) == 1
                                or (
                                    best_confidence >= CONFIDENCE_THRESHOLD and
                                    (
                                        len(candidate_matches) == 1
                                        or best_confidence - candidate_matches[1][1] >= HIGH_CONFIDENCE_DIFF
                                    )
                                )
                            )
                            
                            if has_clear_winner:
                                # High confidence single match - mark as allowed/not allowed
                                # Ensure evidence text is not empty, especially for prohibited instruments
                                evidence_text = reason if reason else (
                                    f"{entry['instrument_category']} is {'allowed' if allowed else 'prohibited'}"
                                )
                                section[best_key]["allowed"] = allowed
                                section[best_key]["confidence"] = best_confidence
                                section[best_key]["note"] = f"Excel mapping: {entry['instrument_category']} - {evidence_text} (Confidence: {best_confidence:.0%})"
                                section[best_key]["evidence"] = {"page": 1, "text": evidence_text}
                                excel_mapping_succeeded = True
                                logger.info(f"✅ EXCEL MAPPING: Mapped '{entry['instrument_category']}' → {type1}/{best_key} = {allowed} (Confidence: {best_confidence:.0%})")
                            else:
                                # Low confidence or multiple similar matches - mark for manual approval with confidence scores
                                top_matches = [m for m in candidate_matches if m[1] >= 0.3]  # Only show matches with >30% confidence
                                for matched_key, confidence in top_matches:
                                    section[matched_key]["allowed"] = None  # None = manual approval required
                                    section[matched_key]["confidence"] = confidence
                                    section[matched_key]["note"] = (
                                        f"Manual approval required: '{entry['instrument_category']}' maps to multiple instruments "
                                        f"({len(top_matches)} candidates, confidence: {confidence:.0%}). "
                                        f"Best match: {best_key} ({best_confidence:.0%}). Original reason: {reason}"
                                    )
                                    evidence_text = reason if reason else (
                                        f"{entry['instrument_category']} requires manual approval"
                                    )
                                    section[matched_key]["evidence"] = {"page": 1, "text": evidence_text}
                                excel_mapping_succeeded = True
                                logger.warning(
                                    f"⚠️ EXCEL MAPPING: '{entry['instrument_category']}' maps to {len(top_matches)} instruments "
                                    f"with confidence {best_confidence:.0%} → Marked for MANUAL APPROVAL: "
                                    f"{[f'{k}({c:.0%})' for k, c in top_matches[:3]]}"
                                )
                        # If still no match but type1 matches, apply to all in section (generic)
                        elif not candidate_matches:
                            # Mapping to entire section - requires manual approval (too ambiguous)
                            manual_approval_count = sum(1 for k in section.keys() if k != "special_other_restrictions")
                            for key in section.keys():
                                if key != "special_other_restrictions":
                                    section[key]["allowed"] = None  # None = manual approval required
                                    section[key]["confidence"] = 0.0  # No confidence for generic section mapping
                                    section[key]["note"] = f"Manual approval required: '{entry['instrument_category']}' maps to entire '{type1}' section ({manual_approval_count} instruments). Original reason: {reason}"
                                    evidence_text = reason if reason else (
                                        f"{entry['instrument_category']} maps to entire '{type1}' section"
                                    )
                                    section[key]["evidence"] = {"page": 1, "text": evidence_text}
                            excel_mapping_succeeded = True
                            logger.warning(f"⚠️ EXCEL MAPPING: '{entry['instrument_category']}' maps to entire '{type1}' section ({manual_approval_count} instruments) → Marked for MANUAL APPROVAL")
                    else:
                        # type1 doesn't match any OCRD section - log warning
                        logger.warning(
                            f"⚠️ EXCEL MAPPING: type1 '{type1}' not found in OCRD sections for instrument "
                            f"'{original_instrument}'. Entry: {entry.get('instrument_category', 'unknown')}"
                        )
                        data["notes"].append(
                            f"[WARNING] Excel mapping found entry for '{original_instrument}' but type1 '{type1}' "
                            "doesn't match OCRD sections. Will try fallback matching."
                        )
                
                # CRITICAL FIX: Only mark as processed if Excel mapping actually succeeded in updating OCRD structure
                if excel_mapping_succeeded:
                    processed_instruments.add(instrument_normalized)
                    logger.info(
                        f"✅ Excel mapping successfully processed '{instrument_normalized}' "
                        "- skipping fallback logic"
                    )
                elif matching_entries:
                    # Excel mapping found entries but couldn't update OCRD (e.g., type1 mismatch)
                    # Don't mark as processed - let fallback logic handle it
                    logger.warning(
                        f"⚠️ Excel mapping found {len(matching_entries)} entries for "
                        f"'{original_instrument}' but failed to update OCRD structure. Will try fallback matching."
                    )
                else:
                    # No matching entries found - will use fallback logic
                    logger.debug(
                        f"Excel mapping found no matches for '{original_instrument}' - will use fallback logic"
                    )

            # Skip if already processed by Excel mapping
            if instrument_normalized in processed_instruments:
                logger.debug(
                    f"Skipping '{instrument_normalized}' - already processed by Excel mapping"
                )
                continue

            # Fallback logic: Use direct instrument matching (when Excel mapping didn't work or isn't available)
            logger.info(
                f"🔄 Using fallback matching for '{original_instrument}' "
                f"(normalized='{instrument_normalized}') - Excel mapping didn't process it"
            )

            # Normalize instrument name (handle underscores, spaces, hyphens)
            instrument_normalized = instrument_normalized.replace("_", " ").replace("-", " ")

            # Build comprehensive mapping of instruments to sections and specific instrument names
            # Includes both English and German terms
            # Note: future, option, and warrant are now top-level sections (no parent "derivatives" category)
            instrument_mapping = {
                # Generic terms (English)
                "bonds": "bond",
                "bond": "bond",
                "equities": "stock",
                "equity": "stock",
                "stocks": "stock",
                "stock": "stock",
                "funds": "fund",
                "fund": "fund",
                "derivatives": "future",  # Map derivatives to future section (default)
                "derivative": "future",  # Map derivative to future section (default)
                "options": "option",
                "option": "option",
                "futures": "future",
                "future": "future",
                "warrants": "warrant",
                "warrant": "warrant",
                "commodities": "commodity",
                "commodity": "commodity",
                "forex": "forex",
                "swaps": "swap",
                "swap": "swap",
                # Generic terms (German)
                "anleihen": "bond",
                "renten": "bond",
                "rentenquote": "bond",
                "aktien": "stock",
                "stammaktien": "stock",
                "vorzugsaktien": "stock",
                "fonds": "fund",
                "aktienfonds": "fund",
                "rentenfonds": "fund",
                "geldmarktfonds": "fund",
                "derivate": "future",
                "optionen": "option",
                "futures": "future",
                "scheine": "warrant",
                "warrants": "warrant",
                "rohstoffe": "commodity",
                "währung": "forex",
                "devisen": "forex",
                "swaps": "swap",
                # Money market instruments (German)
                "geldmarktinstrumente": "deposit",
                "geldmarktprodukte": "deposit",
                "geldmarkt": "deposit",
                # Specific bond types (English)
                "covered bond": "bond",
                "covered_bond": "bond",
                "asset backed security": "bond",
                "asset_backed_security": "bond",
                "asset-backed security": "bond",
                "mortgage bond": "bond",
                "mortgage_bond": "bond",
                "mortgage-bond": "bond",
                "pfandbrief": "bond",
                "pfandbriefe": "bond",
                "convertible bond": "bond",
                "convertible_bond": "bond",
                "commercial paper": "bond",
                "commercial_paper": "bond",
                # Specific bond types (German)
                "staatsanleihen": "bond",
                "corporate bonds": "bond",
                "corporate_bonds": "bond",
                "schatzanweisungen": "bond",
                "bezugsrechte": "right",
                "subscription rights": "right",
                "subscription_rights": "right",
                # Specific stock types (English)
                "common stock": "stock",
                "common_stock": "stock",
                "preferred stock": "stock",
                "preferred_stock": "stock",
                # Specific stock types (German)
                "stammaktien": "stock",
                "common_stock": "stock",
                # Specific fund types (English)
                "equity fund": "fund",
                "equity_fund": "fund",
                "fixed income fund": "fund",
                "fixed_income_fund": "fund",
                "money market fund": "fund",
                "moneymarket_fund": "fund",
                # Specific fund types (German)
                "aktienfonds": "fund",
                "rentenfonds": "fund",
                "geldmarktfonds": "fund",
                # Swaps (German)
                "zinsswaps": "swap",
                "interest swap": "swap",
                "interest_swap": "swap",
                "credit default swap": "swap",
                "credit_default_swap": "swap",
                "total return swap": "swap",
                "total_return_swap": "swap",
                # Forex (German)
                "devisentermingeschäfte": "forex",
                "fx forward": "forex",
                "fx_forward": "forex",
                "forex_outright": "forex",
                "forex_spot": "forex",
                "currency futures": "forex",
                "currency_futures": "forex",
            }
            
            # First try exact match
            lookup_candidates = [instrument_lower, instrument_lower.replace(" ", "_"), instrument_normalized]
            section = None
            for candidate in lookup_candidates:
                if candidate in instrument_mapping:
                    section = instrument_mapping[candidate]
                    break
            if not section and instrument_normalized:
                section = instrument_mapping.get(instrument_normalized)

            # If no exact match, try partial matching
            if not section:
                for key, value in instrument_mapping.items():
                    if key in instrument_normalized or instrument_normalized in key:
                        section = value
                        break

            # If still no match, try to infer from instrument name (English and German)
            if not section:
                instrument_lower_normalized = instrument_normalized.lower()
                # German terms
                if any(term in instrument_lower_normalized for term in ["anleihe", "rente", "pfandbrief", "schatzanweisung"]):
                    section = "bond"
                elif any(term in instrument_lower_normalized for term in ["aktie", "stammaktie", "vorzugsaktie"]):
                    section = "stock"
                elif any(term in instrument_lower_normalized for term in ["fonds", "aktienfonds", "rentenfonds", "geldmarktfonds"]):
                    section = "fund"
                elif any(term in instrument_lower_normalized for term in ["option", "optionen"]):
                    section = "option"
                elif any(term in instrument_lower_normalized for term in ["future", "futures"]):
                    section = "future"
                elif any(term in instrument_lower_normalized for term in ["warrant", "schein", "scheine"]):
                    section = "warrant"
                elif any(term in instrument_lower_normalized for term in ["swap", "swaps", "zinsswap"]):
                    section = "swap"
                elif any(term in instrument_lower_normalized for term in ["rohstoff", "commodity", "edelmetall"]):
                    section = "commodity"
                elif any(term in instrument_lower_normalized for term in ["forex", "währung", "devisen", "currency"]):
                    section = "forex"
                elif any(term in instrument_lower_normalized for term in ["geldmarkt", "money market", "deposit", "kasse", "bankguthaben"]):
                    section = "deposit"
                elif any(term in instrument_lower_normalized for term in ["bezugsrecht", "subscription right", "right"]):
                    section = "rights"
                # English terms (fallback)
                elif "bond" in instrument_lower_normalized:
                    section = "bond"
                elif "stock" in instrument_lower_normalized or "equity" in instrument_lower_normalized:
                    section = "stock"
                elif "fund" in instrument_lower_normalized:
                    section = "fund"
                elif "option" in instrument_lower_normalized:
                    section = "option"
                elif "future" in instrument_lower_normalized:
                    section = "future"
                elif "warrant" in instrument_lower_normalized:
                    section = "warrant"
                elif "swap" in instrument_lower_normalized:
                    section = "swap"
                elif "commodity" in instrument_lower_normalized:
                    section = "commodity"
                elif "forex" in instrument_lower_normalized or "currency" in instrument_lower_normalized:
                    section = "forex"

            # Handle hierarchical sections (tuples) vs flat sections (strings)
            section_path = None
            if section:
                if isinstance(section, tuple):
                    # Hierarchical section: (parent, child)
                    parent, child = section
                    if parent in data["sections"] and child in data["sections"][parent]:
                        section_path = (parent, child)
                elif section in data["sections"]:
                    # Flat section
                    section_path = section
            
            if section_path:
                # Try to match specific instrument names within the section
                instrument_found = False
                
                # Get the actual section data structure (all sections are now flat)
                section_data = data["sections"][section_path]
                
                # Check if instrument name is generic (just "bond", "stock", "fund" without specificity)
                # Also check for German section-level terms
                is_generic = instrument_normalized in [
                    "bond", "bonds", "stock", "stocks", "equity", "equities",
                    "fund", "funds", "derivative", "derivatives", "option", "options",
                    "future", "futures", "warrant", "warrants", "swap", "swaps",
                    "commodity", "commodities", "forex", "currency"
                ] or instrument_normalized.strip() == "forex forwards" or any(
                    term in instrument_normalized.lower() for term in [
                        "rentenquote", "anleihen", "aktien", "geldmarktinstrumente",
                        "bezugsrecht", "bezugsrechte", "gratisaktien"
                    ]
                )

                # Normalize instrument to word list for flexible matching
                instrument_words = set(instrument_normalized.split())
                
                # German-to-English mapping for specific instruments
                german_to_ocrd = {
                    "stammaktien": "common_stock",
                    "common stock": "common_stock",
                    "vorzugsaktien": "preferred_stock",
                    "preferred stock": "preferred_stock",
                    "geldmarktinstrumente": "call_money",  # or time_deposit, cash
                    "geldmarktprodukte": "call_money",
                    "money market": "call_money",
                    "credit default swap": "credit_default_swap",
                    "credit-default-swap": "credit_default_swap",
                    "interest swap": "interest_swap",
                    "zinsswap": "interest_swap",
                    "total return swap": "total_return_swap",
                    "fx forward": "forex_outright",
                    "forex forward": "forex_outright",
                    "devisentermingeschäft": "forex_outright",
                    "currency future": "forex_spot",
                    "devisenfuture": "forex_spot",
                    "bezugsrecht": "subscription_rights",
                    "subscription right": "subscription_rights",
                    "edelmetall": "precious_metal",
                    "precious metal": "precious_metal",
                    # Equity derivatives (critical for matching)
                    "equity future": "single_stock_future",
                    "equity futures": "single_stock_future",
                    "aktienfutures": "single_stock_future",
                    "equity index future": "index_future",
                    "equity index futures": "index_future",
                    "aktienindexfutures": "index_future",
                    "equity option": "stock_option",
                    "equity options": "stock_option",
                    "aktienoptionen": "stock_option",
                    "equity index option": "index_option",
                    "equity index options": "index_option",
                    "aktienindexoptionen": "index_option",
                    # Interest rate futures (critical for correct classification)
                    "interest rate future": "bond_future",
                    "interest rate futures": "bond_future",
                    "interest-rate future": "bond_future",
                    "interest-rate futures": "bond_future",
                    "zinsfutures": "bond_future",
                    "zinsfuture": "bond_future",
                    "zins futures": "bond_future",
                    "zins future": "bond_future",
                    "rentenfutures": "bond_future",
                    "rentenfuture": "bond_future",
                    "renten futures": "bond_future",
                    "renten future": "bond_future",
                    "geldmarktfutures": "bond_future",
                    "geldmarktfuture": "bond_future",
                    "geldmarkt futures": "bond_future",
                    "geldmarkt future": "bond_future",
                    "bond future": "bond_future",
                    "bond futures": "bond_future",
                    "money market future": "bond_future",
                    "money market futures": "bond_future",
                    # Handle German compound terms that might be extracted separately
                    "zinsfutures renten und geldmarktfutures": "bond_future",
                    "zinsfutures renten geldmarktfutures": "bond_future",
                }
                
                # Helper function to get section data (all sections are now flat)
                def get_section_data(section_path):
                    return data["sections"][section_path]
                
                # Helper function to set value in section (all sections are now flat)
                def set_section_value(section_path, key, value_dict):
                    data["sections"][section_path][key].update(value_dict)
                
                # Check if we have a direct German-to-OCRD mapping
                instrument_lower_for_mapping = instrument_normalized.lower().strip()
                if instrument_lower_for_mapping in german_to_ocrd:
                    ocrd_key = german_to_ocrd[instrument_lower_for_mapping]
                    section_data = get_section_data(section_path)
                    if ocrd_key in section_data:
                        # Ensure evidence text is not empty, especially for prohibited instruments
                        evidence_text = reason if reason else (
                            f"{original_instrument} is {'allowed' if allowed else 'prohibited'}"
                        )
                        set_section_value(section_path, ocrd_key, {
                            "allowed": allowed,
                            "confidence": 0.8,
                            "note": f"Instrument rule: {original_instrument} - {evidence_text} (Confidence: 80%)",
                            "evidence": {"page": 1, "text": evidence_text}
                        })
                        logger.info(f"[DEBUG] ✓ Direct German mapping: '{original_instrument}' → '{ocrd_key}' in '{section_path}' (allowed={allowed})")
                        instrument_found = True
                        continue

                section_data = get_section_data(section_path)
                for key in section_data:
                    if key != "special_other_restrictions":
                        # Normalize key name
                        key_normalized = key.replace("_", " ").replace("-", " ")
                        key_words = set(key_normalized.split())
                        
                        # Smart matching function that handles variations
                        def matches_flexibly(instrument_str: str, instrument_word_set: set, key_str: str, key_word_set: set) -> bool:
                            """Check if instrument matches key with flexible word matching"""
                            # Exact match
                            if instrument_str == key_str:
                                return True
                            
                            # One contains the other (handles "commodity certificate" -> "commodity_certificate")
                            if instrument_str in key_str or key_str in instrument_str:
                                return True
                            
                            # Word-based matching: check if all significant words from instrument are in key
                            # Significant words are those with 3+ characters (skip "the", "a", "an", etc.)
                            significant_instrument_words = {w for w in instrument_word_set if len(w) >= 3}
                            significant_key_words = {w for w in key_word_set if len(w) >= 3}
                            
                            # Special handling for equity derivatives:
                            # "equity future" / "equity futures" should match "single_stock_future"
                            # "equity option" / "equity options" should match "stock_option"
                            # "equity index future" should match "index_future"
                            # "equity index option" should match "index_option"
                            # CRITICAL: Any variant of "index future" (equity index future, etc.) should match "index_future"
                            # CRITICAL: Any variant of "index option" (equity index option, etc.) should match "index_option"
                            equity_derivative_mappings = {
                                ("equity", "future"): ("single", "stock", "future"),
                                ("equity", "futures"): ("single", "stock", "future"),
                                ("equity", "option"): ("stock", "option"),
                                ("equity", "options"): ("stock", "option"),
                                ("equity", "index", "future"): ("index", "future"),
                                ("equity", "index", "futures"): ("index", "future"),
                                ("equity", "index", "option"): ("index", "option"),
                                ("equity", "index", "options"): ("index", "option"),
                            }
                            instrument_tuple = tuple(sorted(significant_instrument_words))
                            if instrument_tuple in equity_derivative_mappings:
                                expected_key_words = set(equity_derivative_mappings[instrument_tuple])
                                if expected_key_words.issubset(significant_key_words):
                                    return True
                            
                            # CRITICAL FIX: Handle any variant of index future/option matching to base category
                            # If instrument contains "index" and "future" (or "futures"), and key is "index_future", match it
                            # If instrument contains "index" and "option" (or "options"), and key is "index_option", match it
                            # This ensures "equity index future" -> "index_future" and "equity index option" -> "index_option"
                            has_index = "index" in significant_instrument_words
                            has_future = "future" in significant_instrument_words or "futures" in significant_instrument_words
                            has_option = "option" in significant_instrument_words or "options" in significant_instrument_words
                            
                            # Check if key is index_future
                            is_index_future = "index" in significant_key_words and "future" in significant_key_words
                            # Check if key is index_option
                            is_index_option = "index" in significant_key_words and "option" in significant_key_words
                            
                            # Match any variant of index future to index_future
                            if has_index and has_future and is_index_future:
                                return True
                            
                            # Match any variant of index option to index_option
                            if has_index and has_option and is_index_option:
                                return True
                            
                            # Special handling for interest rate futures:
                            # "interest rate future" / "interest rate futures" / "zinsfutures" should match "bond_future"
                            # "rentenfutures" / "geldmarktfutures" should match "bond_future"
                            # Also handle "Interest rate futures (bond and money market)" -> "bond_future"
                            interest_rate_future_terms = {"interest", "rate", "zins", "renten", "geldmarkt", "bond", "money", "market"}
                            bond_future_terms = {"bond", "future"}
                            
                            # Check if instrument contains interest rate future terms AND future/futures
                            has_interest_rate_terms = bool(interest_rate_future_terms & significant_instrument_words)
                            has_future_term = "future" in significant_instrument_words or "futures" in significant_instrument_words
                            
                            # Check if key is bond_future
                            is_bond_future = bond_future_terms.issubset(significant_key_words)
                            
                            if has_interest_rate_terms and has_future_term and is_bond_future:
                                return True
                            
                            # Also check if instrument contains "bond" and "future" together (for "bond future" variations)
                            if "bond" in significant_instrument_words and has_future_term and is_bond_future:
                                return True
                            
                            # If all significant instrument words are in key words, it's a match
                            # E.g., "commodity certificate" -> ["commodity", "certificate"] both in "commodity_certificate"
                            if significant_instrument_words and significant_instrument_words.issubset(significant_key_words):
                                return True
                            
                            # Reverse: if all significant key words are in instrument words
                            if significant_key_words and significant_key_words.issubset(significant_instrument_words):
                                return True
                            
                            # Partial overlap: if at least 1 significant word matches (reduced from 2 for better matching)
                            # This helps match "equity future" -> "single_stock_future" (both have "future")
                            # E.g., "certificate" should match "commodity_certificate" if certificate is the main word
                            overlap = significant_instrument_words & significant_key_words
                            if len(overlap) >= min(1, len(significant_instrument_words), len(significant_key_words)):
                                # Additional check: if one word matches and it's a key term (future, option, etc.)
                                key_terms = {"future", "futures", "option", "options", "warrant", "warrants", "stock", "equity", "index"}
                                if overlap & key_terms:  # If overlap contains any key term
                                    return True
                            
                            return False
                        
                        # Check if instrument matches this key
                        if matches_flexibly(instrument_normalized, instrument_words, key_normalized, key_words):
                            # Calculate confidence for fallback match (simpler scoring)
                            # Exact match = 0.9, partial match = 0.7, word-based = 0.5
                            if instrument_normalized == key_normalized:
                                confidence = 0.9
                            elif instrument_normalized in key_normalized or key_normalized in instrument_normalized:
                                confidence = 0.7
                            else:
                                confidence = 0.5
                            
                            # Found specific match - only update this one
                            # CRITICAL: Instrument-level rules ALWAYS override section-level rules
                            # This ensures that specific prohibitions (e.g., "Interest rate futures: Not Allowed")
                            # take precedence over general allowances (e.g., "Derivatives: Allowed")
                            # Check current value to preserve explicit prohibitions
                            current_allowed = get_section_data(section_path)[key].get("allowed")
                            current_note = get_section_data(section_path)[key].get("note", "")
                            
                            # If this is an instrument-level rule, it ALWAYS overrides section-level rules
                            # Even if a section-level rule was already applied
                            is_instrument_level_rule = "Instrument rule:" in current_note or current_note.startswith("Instrument rule:")
                            is_section_level_rule = "Section-level rule:" in current_note or current_note.startswith("Section-level rule:")
                            
                            # Instrument-level rules always win, regardless of what was there before
                            # Ensure evidence text is not empty, especially for prohibited instruments
                            evidence_text = reason if reason else (
                                f"{original_instrument} is {'allowed' if allowed else 'prohibited'}"
                            )
                            set_section_value(section_path, key, {
                                "allowed": allowed,
                                "confidence": confidence,
                                "note": f"Instrument rule: {original_instrument} - {evidence_text} (Confidence: {confidence:.0%})",
                                "evidence": {
                                    "page": 1,
                                    "text": evidence_text
                                }
                            })
                            if is_section_level_rule:
                                logger.info(
                                    f"🔄 OVERRIDE: Instrument-level rule for '{original_instrument}' → '{key}' "
                                    f"(allowed={allowed}) is overriding previous section-level rule "
                                    f"(previous allowed={current_allowed})"
                                )
                            instrument_found = True
                            match_msg = (
                                f"[DEBUG] ✓ Matched '{original_instrument}' "
                                f"(normalized='{instrument_normalized}') → '{key}' in '{section_path}' "
                                f"(allowed={allowed}, confidence={confidence:.0%})"
                            )
                            logger.info(match_msg)  # Changed to info level for better visibility
                            data["notes"].append(match_msg)  # Add to notes for visibility
                            break  # Stop after first match to avoid duplicate matches

                # CRITICAL: For generic terms or section-level matches, if LLM says allowed=True, mark all as allowed
                # Also handle cases where no specific match was found but we have a section
                # IMPORTANT: Explicit "not allowed" rules for subtypes take precedence over parent "allowed" rules
                if not instrument_found:
                    # Special handling for derivative parent category - apply to all subtypes (future, option, warrant)
                    is_derivatives_parent = (
                        isinstance(section_path, tuple) and 
                        section_path[0] == "derivative" and
                        original_instrument.lower() in ["derivatives", "derivate", "derivative"]
                    )
                    
                    # Standard section-level rule handling
                    if not instrument_found:
                        section_data = get_section_data(section_path)
                        instrument_count = sum(1 for k in section_data.keys() if k != "special_other_restrictions")
                        
                        # CRITICAL: For derivatives (future, option, warrant), section-level rules are NOT sufficient
                        # Require explicit instrument-level rules for derivatives
                        is_derivative_section = section_path in ["future", "option", "warrant"]
                        
                        if is_derivative_section:
                            # For derivatives, section-level rules are too risky - require explicit instrument-level rules
                            logger.warning(
                                f"⚠️ CONSERVATIVE: Section-level rule '{original_instrument}' (allowed={allowed}) "
                                f"for derivative section '{section_path}' is IGNORED. "
                                f"Derivatives require explicit instrument-level rules for safety. "
                                f"This rule will NOT be applied to any instruments in this section."
                            )
                            data["notes"].append(
                                f"WARNING: Section-level rule '{original_instrument}' for {section_path} section was ignored. "
                                f"Derivatives require explicit instrument-level rules (e.g., 'Equity futures: Allowed' not 'Derivatives: Allowed')."
                            )
                            instrument_found = True  # Mark as processed so we don't try to apply it
                            continue  # Skip applying this section-level rule
                        
                        # If LLM explicitly said allowed=True, trust it and mark all instruments in section as allowed
                        # This handles section-level rules like "Rentenquote (nur Renten)" = all bonds allowed
                        # BUT: Do NOT overwrite instruments that are explicitly marked as not allowed (False)
                        # NOTE: This only applies to non-derivative sections (derivatives handled above)
                        if allowed:
                            current_data = get_section_data(section_path)
                            allowed_count = 0
                            skipped_prohibited_count = 0
                            
                            logger.info(
                                f"✅ LLM marked '{original_instrument}' as allowed=True → "
                                f"checking {instrument_count} instruments in '{section_path}' section"
                            )
                            
                            for key in section_data:
                                if key != "special_other_restrictions":
                                    current_allowed = current_data[key]["allowed"]
                                    current_note = current_data[key].get("note", "")
                                    
                                    # CRITICAL: Instrument-level rules ALWAYS take precedence over section-level rules
                                    # Check if there's already an instrument-level rule (even if it's allowed=True)
                                    is_instrument_level_rule = "Instrument rule:" in current_note or current_note.startswith("Instrument rule:")
                                    
                                    # CRITICAL: Explicit "not allowed" (False) takes precedence over parent "allowed" (True)
                                    # Also: Instrument-level rules take precedence over section-level rules
                                    # Only mark as allowed if:
                                    # 1. Not already explicitly set to False (prohibited)
                                    # 2. Not already set by an instrument-level rule
                                    # 3. Currently None (not yet determined)
                                    if current_allowed is False:
                                        # This instrument was explicitly prohibited - preserve the prohibition
                                        skipped_prohibited_count += 1
                                        # Ensure evidence is populated even if it was empty
                                        current_evidence = current_data[key].get("evidence", {})
                                        if not current_evidence.get("text"):
                                            evidence_text = reason if reason else f"{original_instrument} is explicitly prohibited"
                                            current_data[key]["evidence"] = {"page": 1, "text": evidence_text}
                                            if not current_data[key].get("note"):
                                                current_data[key]["note"] = f"Instrument rule: {original_instrument} - {evidence_text}"
                                        logger.debug(
                                            f"⚠️ Skipping '{key}' in '{section_path}': "
                                            f"explicitly prohibited (allowed=False) - parent allowance does not override"
                                        )
                                    elif is_instrument_level_rule:
                                        # There's already an instrument-level rule - don't override it with section-level rule
                                        skipped_prohibited_count += 1
                                        logger.debug(
                                            f"⚠️ Skipping '{key}' in '{section_path}': "
                                            f"already has instrument-level rule (note: '{current_note[:50]}...') - "
                                            f"section-level rule does not override instrument-level rules"
                                        )
                                    elif current_allowed is None:
                                        # Not yet determined - apply parent allowance
                                        evidence_text = reason if reason else f"{original_instrument} is allowed"
                                        set_section_value(section_path, key, {
                                            "allowed": True,
                                            "confidence": 0.7,  # Medium confidence for section-level match
                                            "note": f"Section-level rule: {original_instrument} - {evidence_text} (Confidence: 70%)",
                                            "evidence": {
                                                "page": 1,
                                                "text": evidence_text
                                            }
                                        })
                                        allowed_count += 1
                                    # If current_allowed is already True, leave it as is (don't overwrite)
                            
                            instrument_found = True
                            logger.info(
                                f"✅ Section-level rule applied: marked {allowed_count} instruments as ALLOWED "
                                f"(skipped {skipped_prohibited_count} explicitly prohibited instruments) "
                                f"in '{section_path}' section based on LLM rule: '{original_instrument}'"
                            )
                            
                            if skipped_prohibited_count > 0:
                                logger.warning(
                                    f"⚠️ IMPORTANT: {skipped_prohibited_count} instruments in '{section_path}' section "
                                    f"were explicitly prohibited and were NOT overridden by parent category allowance. "
                                    f"This is correct behavior - explicit subtype prohibitions take precedence."
                                )
                    elif is_generic:
                        # If LLM said not allowed or unclear AND it's generic, mark for manual approval
                        logger.warning(
                            f"⚠️ Generic instrument term '{original_instrument}' "
                            f"(normalized='{instrument_normalized}') maps to entire '{section_path}' section "
                            f"({instrument_count} instruments) → Marked for MANUAL APPROVAL"
                        )
                        for key in section_data:
                            if key != "special_other_restrictions":
                                # Only set to None if not already set
                                current_data = get_section_data(section_path)
                                if current_data[key]["allowed"] is None:
                                    set_section_value(section_path, key, {
                                        "allowed": None,  # None = manual approval required
                                        "confidence": 0.0,  # No confidence for generic section mapping
                                        "note": f"Manual approval required: Generic term '{original_instrument}' maps to entire '{section_path}' section ({instrument_count} instruments). Original reason: {reason}",
                                        "evidence": {
                                            "page": 1,
                                            "text": reason
                                        }
                                    })
                        instrument_found = True
                        generic_msg = (
                            f"Generic instrument rule '{original_instrument}' requires manual approval: "
                            f"maps to entire '{section}' section ({instrument_count} instruments). "
                            f"Original reason: {reason}"
                        )
                        logger.warning(f"⚠️ {generic_msg}")
                        data["notes"].append(generic_msg)
                elif not instrument_found and section_path:
                    # Non-generic term but no match - mark as manual approval (ambiguous)
                    section_data = get_section_data(section_path)
                    manual_approval_count = sum(1 for k in section_data.keys() if k != "special_other_restrictions")
                    logger.warning(
                        f"⚠️ Could not match instrument '{original_instrument}' "
                        f"(normalized='{instrument_normalized}') to specific instrument in '{section_path}', "
                        f"mapping to entire section ({manual_approval_count} instruments) → Marked for MANUAL APPROVAL"
                    )
                    for key in section_data:
                        if key != "special_other_restrictions":
                            set_section_value(section_path, key, {
                                "allowed": None,  # None = manual approval required
                                "confidence": 0.0,  # No confidence for unmatched section mapping
                                "note": f"Manual approval required: Unmatched instrument '{original_instrument}' maps to entire '{section_path}' section ({manual_approval_count} instruments). Original reason: {reason}",
                                "evidence": {
                                    "page": 1,
                                    "text": reason if reason else f"Unmatched instrument '{original_instrument}' requires manual approval"
                                }
                            })
                    unmatched_msg = (
                        f"Unmatched instrument rule '{original_instrument}' requires manual approval: "
                        f"maps to entire '{section}' section ({manual_approval_count} instruments). "
                        f"Original reason: {reason}"
                    )
                    logger.warning(f"⚠️ {unmatched_msg}")
                    data["notes"].append(unmatched_msg)
                elif not section:
                    # Couldn't even determine which section this belongs to
                    logger.error(
                        f"Could not determine section for instrument '{original_instrument}' "
                        f"(normalized='{instrument_normalized}')"
                    )
                    data["notes"].append(
                        f"ERROR: Unmatched instrument rule '{original_instrument}' "
                        f"(normalized='{instrument_normalized}') = {'Allowed' if allowed else 'Not Allowed'}. "
                        f"Could not determine instrument category. Reason: {reason}"
                    )
        
        # Add conflicts to notes (using validated response)
        for conflict in validated_response.conflicts:
            data["notes"].append(f"Conflict: {conflict.category} - {conflict.detail}")
        
        # PRE-PROCESSING: Ensure index future/option variants are matched correctly
        # CRITICAL: If any variant of "index future" or "index option" was found in the document,
        # apply that rule to the base "index_future" or "index_option" category
        logger.info("🔍 Pre-processing: Checking for index future/option variant matches...")
        index_future_variants = [
            "equity index future", "equity index futures", "aktienindexfutures",
            "equity-index-future", "equity-index-futures", "index future", "index futures"
        ]
        index_option_variants = [
            "equity index option", "equity index options", "aktienindexoptionen",
            "equity-index-option", "equity-index-options", "index option", "index options"
        ]
        
        # Check if any variant was found in the LLM response (use instrument_rules from the loop above)
        # We need to check the original instrument_rules list that was processed
        # Since we already processed them, we'll check the sections to see if any variant was matched
        # But we can also check the original rules by looking at what was extracted
        # Actually, the best approach is to check the sections after matching and look for any variant matches
        # that might have been missed. Let's check if we have any rules that contain index future/option variants
        # by examining what was actually matched in the previous loop
        
        # Re-check instrument_rules to find variants that might not have matched
        for rule in instrument_rules:
            instrument_normalized = self._normalize_instrument_name(rule.instrument)
            instrument_lower = instrument_normalized.lower()
            
            # Check if this is an index future variant
            is_index_future_variant = any(variant in instrument_lower for variant in index_future_variants)
            # Check if this is an index option variant  
            is_index_option_variant = any(variant in instrument_lower for variant in index_option_variants)
            
            if is_index_future_variant and "future" in data["sections"]:
                # Apply this rule to index_future
                if "index_future" in data["sections"]["future"]:
                    current_value = data["sections"]["future"]["index_future"]
                    # Only apply if not already set by explicit rule, or if this is more specific
                    if current_value.get("allowed") is None or "conservative default" in current_value.get("note", ""):
                        evidence_text = rule.reason if rule.reason else f"{rule.instrument} is {'allowed' if rule.allowed else 'prohibited'}"
                        data["sections"]["future"]["index_future"] = {
                            "allowed": rule.allowed,
                            "confidence": 0.8,
                            "note": f"Instrument rule: {rule.instrument} → index_future - {evidence_text} (Confidence: 80%)",
                            "evidence": {"page": 1, "text": evidence_text}
                        }
                        logger.info(f"✅ Mapped '{rule.instrument}' → 'index_future' (allowed={rule.allowed})")
            
            if is_index_option_variant and "option" in data["sections"]:
                # Apply this rule to index_option
                if "index_option" in data["sections"]["option"]:
                    current_value = data["sections"]["option"]["index_option"]
                    # Only apply if not already set by explicit rule, or if this is more specific
                    if current_value.get("allowed") is None or "conservative default" in current_value.get("note", ""):
                        evidence_text = rule.reason if rule.reason else f"{rule.instrument} is {'allowed' if rule.allowed else 'prohibited'}"
                        data["sections"]["option"]["index_option"] = {
                            "allowed": rule.allowed,
                            "confidence": 0.8,
                            "note": f"Instrument rule: {rule.instrument} → index_option - {evidence_text} (Confidence: 80%)",
                            "evidence": {"page": 1, "text": evidence_text}
                        }
                        logger.info(f"✅ Mapped '{rule.instrument}' → 'index_option' (allowed={rule.allowed})")
        
        # POST-PROCESSING: 
        # CRITICAL: Conservative approach for derivatives - default to NOT ALLOWED unless explicitly allowed
        # 1. Ensure all instruments marked as prohibited (allowed=False) have evidence text populated
        # 2. For derivatives (future, option, warrant): Set to NOT ALLOWED if no explicit rule found (conservative default)
        logger.info("🔍 Post-processing: Applying conservative defaults for derivatives and ensuring evidence text...")
        evidence_fixed_count = 0
        derivatives_set_to_prohibited = 0
        derivative_sections = ["future", "option", "warrant"]  # These are now top-level sections
        
        for section_name, section_data in data["sections"].items():
            if isinstance(section_data, dict):
                # Handle all sections as flat (including future, option, warrant which are now top-level)
                for key, value in section_data.items():
                    if key != "special_other_restrictions" and isinstance(value, dict):
                        current_allowed = value.get("allowed")
                        evidence = value.get("evidence", {})
                        evidence_text = evidence.get("text", "")
                        current_note = value.get("note", "")
                        
                        # CRITICAL: Conservative handling for derivative sections (future, option, warrant)
                        if section_name in derivative_sections:
                            # Check if this was set by an explicit instrument-level rule
                            is_explicit_instrument_rule = (
                                "Instrument rule:" in current_note or 
                                current_note.startswith("Instrument rule:") or
                                (current_allowed is not None and evidence_text and len(evidence_text.strip()) > 10)
                            )
                            
                            # Check if this was set by a section-level rule (less reliable for derivatives)
                            is_section_level_rule = (
                                "Section-level rule:" in current_note or 
                                current_note.startswith("Section-level rule:")
                            )
                            
                            if current_allowed is True:
                                # Only allow if there's explicit evidence (not just section-level rule)
                                if is_section_level_rule and not is_explicit_instrument_rule:
                                    # Section-level rule for derivatives is not reliable - require explicit instrument rule
                                    logger.warning(
                                        f"⚠️ CONSERVATIVE: {section_name}.{key} was marked allowed by section-level rule, "
                                        f"but no explicit instrument-level rule found. Setting to NOT ALLOWED (conservative default)."
                                    )
                                    value["allowed"] = False
                                    value["note"] = f"NOT ALLOWED (conservative default): No explicit instrument-level rule found for {key.replace('_', ' ').title()}. Section-level rules are not sufficient for derivatives."
                                    value["evidence"] = {
                                        "page": None,
                                        "text": f"No explicit rule found in document for {key.replace('_', ' ').title()}. Conservative default: NOT ALLOWED."
                                    }
                                    derivatives_set_to_prohibited += 1
                                elif not evidence_text or len(evidence_text.strip()) < 10:
                                    # Even with instrument rule, need good evidence
                                    logger.warning(
                                        f"⚠️ CONSERVATIVE: {section_name}.{key} marked allowed but evidence is insufficient. "
                                        f"Setting to NOT ALLOWED (conservative default)."
                                    )
                                    value["allowed"] = False
                                    value["note"] = f"NOT ALLOWED (conservative default): Insufficient evidence for {key.replace('_', ' ').title()}"
                                    value["evidence"] = {
                                        "page": None,
                                        "text": f"Insufficient evidence found for {key.replace('_', ' ').title()}. Conservative default: NOT ALLOWED."
                                    }
                                    derivatives_set_to_prohibited += 1
                                else:
                                    # Has explicit instrument rule with good evidence - keep as allowed
                                    logger.debug(f"✅ Keeping {section_name}.{key} as allowed=True (explicit instrument rule with evidence)")
                            elif current_allowed is None:
                                # No rule found - conservative default: NOT ALLOWED
                                logger.info(
                                    f"ℹ️ CONSERVATIVE: {section_name}.{key} has no explicit rule → Setting to NOT ALLOWED (conservative default)"
                                )
                                value["allowed"] = False
                                value["note"] = f"NOT ALLOWED (conservative default): No explicit rule found in document for {key.replace('_', ' ').title()}"
                                value["evidence"] = {
                                    "page": None,
                                    "text": f"No explicit rule found in document for {key.replace('_', ' ').title()}. Conservative default: NOT ALLOWED."
                                }
                                derivatives_set_to_prohibited += 1
                            elif current_allowed is False:
                                # Already prohibited - ensure evidence is populated
                                if not evidence_text or len(evidence_text.strip()) < 5:
                                    instrument_name = key.replace("_", " ").title()
                                    evidence_text = f"{instrument_name} is explicitly prohibited"
                                    value["evidence"] = {"page": 1, "text": evidence_text}
                                    if not value.get("note") or "conservative default" not in value.get("note", ""):
                                        value["note"] = f"Instrument rule: {instrument_name} - {evidence_text}"
                                    evidence_fixed_count += 1
                        else:
                            # Handle non-derivative sections (bond, stock, fund, etc.) - standard behavior
                            if current_allowed is False:
                                if not evidence_text:
                                    # Generate default evidence text for prohibited instruments
                                    instrument_name = key.replace("_", " ").title()
                                    evidence_text = f"{instrument_name} is explicitly prohibited"
                                    value["evidence"] = {"page": 1, "text": evidence_text}
                                    if not value.get("note"):
                                        value["note"] = f"Instrument rule: {instrument_name} - {evidence_text}"
                                    evidence_fixed_count += 1
                                    logger.debug(f"✅ Fixed missing evidence for prohibited instrument: {section_name}.{key}")
        
        if derivatives_set_to_prohibited > 0:
            logger.warning(f"⚠️ CONSERVATIVE DEFAULT: Set {derivatives_set_to_prohibited} derivative instruments to NOT ALLOWED (no explicit rule found or insufficient evidence)")
        if evidence_fixed_count > 0:
            logger.info(f"✅ Post-processing complete: Fixed evidence for {evidence_fixed_count} prohibited instruments")
        
        # DEBUG: Log derivative status summary (as suggested by GPT)
        # Note: future, option, and warrant are now top-level sections (no parent "derivatives" category)
        derivative_sections = ["future", "option", "warrant"]
        for section_name in derivative_sections:
            if section_name in data["sections"]:
                logger.info(f"🔍 [DEBUG] {section_name.upper()} status summary after post-processing:")
                section_data = data["sections"][section_name]
                summary = {
                    key: value.get("allowed")
                    for key, value in section_data.items()
                    if isinstance(value, dict) and key != "special_other_restrictions"
                }
                # Count by status
                allowed_count = sum(1 for v in summary.values() if v is True)
                prohibited_count = sum(1 for v in summary.values() if v is False)
                undetermined_count = sum(1 for v in summary.values() if v is None)
                logger.info(
                    f"  {section_name.upper()}: Allowed={allowed_count}, Prohibited={prohibited_count}, "
                    f"Undetermined={undetermined_count} (Total: {len(summary)})"
                )
                # Show sample of first few instruments
                sample_items = list(summary.items())[:3]
                if sample_items:
                    logger.info(f"    Sample: {dict(sample_items)}")
        
        # No parent "Derivatives" category post-processing needed - future, option, warrant are now top-level sections
        
        # Final debug: Count how many instruments were actually set to allowed, prohibited, or manual approval
        final_allowed_count = sum(
            1 for section in data["sections"].values()
            for key, value in section.items()
            if isinstance(value, dict) and value.get("allowed") is True
        )
        
        final_prohibited_count = sum(
            1 for section in data["sections"].values()
            for key, value in section.items()
            if isinstance(value, dict) and value.get("allowed") is False
        )
        
        final_manual_approval_count = sum(
            1 for section in data["sections"].values()
            for key, value in section.items()
            if isinstance(value, dict) and value.get("allowed") is None and value.get("note", "").startswith("Manual approval required")
        )
        
        # Count total instruments
        total_instruments_count = sum(
            1 for section in data["sections"].values()
            for key, value in section.items()
            if isinstance(value, dict) and "allowed" in value
        )
        
        final_debug = f"[DEBUG] After processing: {final_allowed_count} allowed, {final_prohibited_count} prohibited, {final_manual_approval_count} require manual approval (out of {total_instruments_count} total OCRD instruments)"
        data["notes"].append(final_debug)
        logger.info(f"✅ {final_debug}")
        
        if final_allowed_count == 0:
            logger.warning(f"⚠️ {final_debug} - This might indicate a problem!")
            data["notes"].append(
                "[WARNING] No instruments were marked as allowed. Check logs for details about why rules weren't applied."
            )
        else:
            logger.info(f"✅ {final_debug}")
        
        # DEBUG: Log derivative section status summary (future, option, warrant are now top-level)
        derivative_sections = ["future", "option", "warrant"]
        for section_name in derivative_sections:
            if section_name in data["sections"]:
                section_data = data["sections"][section_name]
                summary = {
                    key: value.get("allowed")
                    for key, value in section_data.items()
                    if isinstance(value, dict) and key != "special_other_restrictions"
                }
                # Count by status for quick diagnosis
                true_count = sum(1 for v in summary.values() if v is True)
                false_count = sum(1 for v in summary.values() if v is False)
                none_count = sum(1 for v in summary.values() if v is None)
                logger.info(
                    f"  {section_name}: True={true_count}, False={false_count}, None={none_count} "
                    f"(Total: {len(summary)})"
                )
                # Show sample of first 3-5 instruments for detailed inspection
                sample = dict(list(summary.items())[:5])
                if sample:
                    logger.debug(f"    Sample states: {sample}")
        
        return data

    def _calculate_metrics(self, data: Dict[str, Any]) -> tuple:
        """Calculate analysis metrics"""
        total_instruments = 0
        allowed_instruments = 0
        evidence_count = 0
        
        for section, items in data.get("sections", {}).items():
            for key, value in items.items():
                if isinstance(value, dict) and "allowed" in value:
                    total_instruments += 1
                    if value.get("allowed"):
                        allowed_instruments += 1
                        if value.get("evidence", {}).get("text"):
                            evidence_count += 1
        
        evidence_coverage = int((evidence_count / allowed_instruments * 100)) if allowed_instruments > 0 else 0
        
        return total_instruments, allowed_instruments, evidence_coverage
    
    def _calculate_confidence_score(self, data: Dict[str, Any], evidence_coverage: int, model: str, raw_analysis: Dict[str, Any]) -> int:
        """
        Calculate confidence score (0-100) based on:
        - Evidence quality and coverage
        - Model type (gpt-5 has higher base confidence)
        - Number of conflicts found
        - Evidence text quality (length, specificity)
        """
        base_score = 50  # Start with 50%
        
        # Model confidence boost
        model_confidence_boost = {
            "gpt-5.2": 35,  # Latest and most capable model (used for vision analysis)
            "gpt-5.1": 30,  # Previous latest model
            "gpt-5": 25,  # Latest and most capable model
            "gpt-4o": 20,  # High quality model
            "gpt-4o-mini": 10,  # Fast, good quality model
        }
        base_score += model_confidence_boost.get(model.lower(), 5)
        
        # Evidence coverage (0-25 points)
        evidence_score = (evidence_coverage / 100) * 25
        base_score += evidence_score
        
        # Evidence quality (0-15 points)
        evidence_quality_score = 0
        evidence_length_sum = 0
        evidence_count = 0
        
        for section, items in data.get("sections", {}).items():
            for key, value in items.items():
                if isinstance(value, dict) and value.get("allowed"):
                    evidence_text = value.get("evidence", {}).get("text", "")
                    if evidence_text:
                        evidence_length_sum += len(evidence_text)
                        evidence_count += 1
        
        if evidence_count > 0:
            avg_evidence_length = evidence_length_sum / evidence_count
            # Longer evidence texts (more specific) = higher confidence
            # 50 chars = 5 points, 100 chars = 10 points, 200+ chars = 15 points
            if avg_evidence_length >= 200:
                evidence_quality_score = 15
            elif avg_evidence_length >= 100:
                evidence_quality_score = 10
            elif avg_evidence_length >= 50:
                evidence_quality_score = 5
        
        base_score += evidence_quality_score
        
        # Conflicts penalty (0-10 points deduction)
        conflicts = raw_analysis.get("conflicts", [])
        conflicts_penalty = min(len(conflicts) * 2, 10)  # Max 10 point deduction
        base_score -= conflicts_penalty
        
        # Total rules found (0-10 points)
        # More rules extracted = better understanding
        sector_rules = len(raw_analysis.get("sector_rules", []))
        country_rules = len(raw_analysis.get("country_rules", []))
        instrument_rules = len(raw_analysis.get("instrument_rules", []))
        total_rules = sector_rules + country_rules + instrument_rules
        
        if total_rules >= 10:
            base_score += 10
        elif total_rules >= 5:
            base_score += 5
        elif total_rules >= 2:
            base_score += 2
        
        # Ensure score is between 0 and 100
        confidence_score = max(0, min(100, int(base_score)))
        
        return confidence_score
    
    async def create_excel_from_llm_response(self, llm_response: Dict[str, Any], filename: str = None) -> str:
        """Create Excel export from validated LLM response"""
        try:
            # Convert LLM response to OCRD format (includes validation)
            ocrd_data = self._convert_llm_response_to_ocrd_format(llm_response)
            
            # Create Excel export
            excel_path = await self.file_handler.create_excel_export(ocrd_data)
            
            return excel_path
            
        except Exception as e:
            raise Exception(f"Failed to create Excel from LLM response: {str(e)}")
    
    def validate_and_preview_llm_response(self, llm_response: Dict[str, Any]) -> Dict[str, Any]:
        """Validate LLM response and return preview for debugging"""
        try:
            # Validate the response (returns LLMResponse object)
            validated_response = self._validate_llm_response(llm_response)
            
            # Return preview using validated response
            preview = {
                "valid": True,
                "sector_rules_count": len(validated_response.sector_rules),
                "country_rules_count": len(validated_response.country_rules),
                "instrument_rules_count": len(validated_response.instrument_rules),
                "conflicts_count": len(validated_response.conflicts),
                "preview": {
                    "sector_rules": [r.model_dump() for r in validated_response.sector_rules[:3]],
                    "country_rules": [r.model_dump() for r in validated_response.country_rules[:3]],
                    "instrument_rules": [r.model_dump() for r in validated_response.instrument_rules[:3]],
                    "conflicts": [c.model_dump() for c in validated_response.conflicts[:3]]
                }
            }
            
            return preview
            
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "llm_response": llm_response
            }
