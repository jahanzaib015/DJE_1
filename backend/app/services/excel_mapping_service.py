"""
Excel Mapping Service
Loads and manages the instrument/category mapping table from Excel.
This service provides normalization and matching between PDF terms and standard taxonomy.
"""
import os
import pandas as pd
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import re
from ..utils.logger import setup_logger

logger = setup_logger(__name__)


class ExcelMappingService:
    """Service for managing Excel-based instrument/category mapping"""
    
    def __init__(self, excel_path: Optional[str] = None):
        """
        Initialize the Excel mapping service.
        
        Args:
            excel_path: Path to Excel file. If None, uses default location or loads from code.
        """
        self.mapping_data: List[Dict] = []
        self.instrument_lookup: Dict[str, List[Dict]] = {}  # instrument -> list of matching entries
        self.asset_tree_lookup: Dict[str, Dict[str, List[Dict]]] = {}  # type1 -> type2 -> type3 -> entries
        
        if excel_path and os.path.exists(excel_path):
            self.load_from_excel(excel_path)
        else:
            # Load from embedded data (will be populated from Excel)
            self._load_from_code()
    
    def load_from_excel(self, excel_path: str) -> None:
        """
        Load mapping data from Excel file.
        
        Expected columns:
        - Column A: Instrument/Category
        - Column B: hint/notice
        - Column C: Asset Tree Type1
        - Column D: Asset Tree Type2
        - Column E: Asset Tree Type3
        - Column F: restriction
        - Column G: allowed (tick column - will be filled)
        """
        try:
            # Read Excel file
            df = pd.read_excel(excel_path, sheet_name=0, header=0)
            
            # Ensure we have the right columns
            required_columns = ['Instrument/Category', 'hint/notice', 'Asset Tree Type1', 
                              'Asset Tree Type2', 'Asset Tree Type3', 'restriction']
            
            # Rename columns if needed (handle different header names)
            column_mapping = {}
            for i, col in enumerate(df.columns):
                col_lower = str(col).lower().strip()
                if i == 0 or 'instrument' in col_lower or 'category' in col_lower:
                    column_mapping[col] = 'Instrument/Category'
                elif i == 1 or 'hint' in col_lower or 'notice' in col_lower:
                    column_mapping[col] = 'hint/notice'
                elif i == 2 or 'type1' in col_lower or 'asset tree type1' in col_lower:
                    column_mapping[col] = 'Asset Tree Type1'
                elif i == 3 or 'type2' in col_lower or 'asset tree type2' in col_lower:
                    column_mapping[col] = 'Asset Tree Type2'
                elif i == 4 or 'type3' in col_lower or 'asset tree type3' in col_lower:
                    column_mapping[col] = 'Asset Tree Type3'
                elif i == 5 or 'restriction' in col_lower:
                    column_mapping[col] = 'restriction'
            
            df = df.rename(columns=column_mapping)
            
            # Convert to list of dictionaries
            self.mapping_data = []
            for idx, row in df.iterrows():
                entry = {
                    'row_id': idx + 2,  # Excel row number (assuming header at row 1)
                    'instrument_category': str(row.get('Instrument/Category', '')).strip(),
                    'hint_notice': str(row.get('hint/notice', '')).strip(),
                    'asset_tree_type1': str(row.get('Asset Tree Type1', '')).strip(),
                    'asset_tree_type2': str(row.get('Asset Tree Type2', '')).strip(),
                    'asset_tree_type3': str(row.get('Asset Tree Type3', '')).strip(),
                    'restriction': str(row.get('restriction', '')).strip(),
                    'allowed': None  # Will be filled during analysis
                }
                
                # Skip empty rows
                if not entry['instrument_category'] or entry['instrument_category'] == 'nan':
                    continue
                
                self.mapping_data.append(entry)
            
            # Build lookup indexes
            self._build_lookup_indexes()
            
            logger.info(f"✅ Loaded {len(self.mapping_data)} entries from Excel file: {excel_path}")
            logger.info(f"📊 Built lookup index with {len(self.instrument_lookup)} instrument keys")
            # Log sample of instrument names for debugging
            sample_keys = list(self.instrument_lookup.keys())[:10]
            logger.info(f"📋 Sample instrument names in lookup: {sample_keys}")
            
        except Exception as e:
            logger.error(f"Error loading Excel file: {e}", exc_info=True)
            raise Exception(f"Failed to load Excel mapping file: {str(e)}")
    
    def _load_from_code(self) -> None:
        """
        Load mapping data from embedded code structure.
        This will be populated from the Excel file you provide.
        """
        try:
            # Try to import embedded mapping data
            from ..utils.embedded_mapping import MAPPING_DATA
            self.mapping_data = MAPPING_DATA
            self._build_lookup_indexes()
            logger.info(f"Excel mapping loaded from embedded code: {len(self.mapping_data)} entries")
        except ImportError:
            # Fallback: empty mapping if embedded file doesn't exist
            self.mapping_data = []
            self._build_lookup_indexes()
            logger.info("Excel mapping loaded from code (empty - run load_excel_mapping.py to populate)")
    
    def _build_lookup_indexes(self) -> None:
        """Build fast lookup indexes for matching"""
        self.instrument_lookup = {}
        self.asset_tree_lookup = {}
        
        for entry in self.mapping_data:
            instrument = entry['instrument_category'].lower().strip()
            
            # Build instrument lookup (handles variations)
            if instrument:
                # Direct match
                if instrument not in self.instrument_lookup:
                    self.instrument_lookup[instrument] = []
                self.instrument_lookup[instrument].append(entry)
                
                # Also index by words (for partial matching)
                words = re.findall(r'\w+', instrument)
                for word in words:
                    if len(word) > 3:  # Only index meaningful words
                        if word not in self.instrument_lookup:
                            self.instrument_lookup[word] = []
                        if entry not in self.instrument_lookup[word]:
                            self.instrument_lookup[word].append(entry)
            
            # Build asset tree lookup
            type1 = entry['asset_tree_type1'].lower().strip()
            type2 = entry['asset_tree_type2'].lower().strip()
            type3 = entry['asset_tree_type3'].lower().strip()
            
            if type1:
                if type1 not in self.asset_tree_lookup:
                    self.asset_tree_lookup[type1] = {}
                if type2:
                    if type2 not in self.asset_tree_lookup[type1]:
                        self.asset_tree_lookup[type1][type2] = {}
                    if type3:
                        if type3 not in self.asset_tree_lookup[type1][type2]:
                            self.asset_tree_lookup[type1][type2][type3] = []
                        self.asset_tree_lookup[type1][type2][type3].append(entry)
                    else:
                        # Store at type2 level if no type3
                        if 'default' not in self.asset_tree_lookup[type1][type2]:
                            self.asset_tree_lookup[type1][type2]['default'] = []
                        self.asset_tree_lookup[type1][type2]['default'].append(entry)
                else:
                    # Store at type1 level if no type2
                    if 'default' not in self.asset_tree_lookup[type1]:
                        self.asset_tree_lookup[type1]['default'] = {}
                    if 'default' not in self.asset_tree_lookup[type1]['default']:
                        self.asset_tree_lookup[type1]['default']['default'] = []
                    self.asset_tree_lookup[type1]['default']['default'].append(entry)
    
    def find_matching_entries(self, extracted_term: str, context: Optional[str] = None) -> List[Dict]:
        """
        Find matching entries for an extracted term from PDF.
        
        Args:
            extracted_term: Term extracted by OpenAI from PDF
            context: Surrounding context (for negative logic detection)
        
        Returns:
            List of matching mapping entries
        """
        extracted_term = extracted_term.lower().strip()
        matches = []
        
        logger.debug(f"🔍 Searching for matches for: '{extracted_term}' (lookup has {len(self.instrument_lookup)} entries)")
        
        # Direct match
        if extracted_term in self.instrument_lookup:
            matches.extend(self.instrument_lookup[extracted_term])
            logger.debug(f"✅ Direct match found: {len(matches)} entries")
        
        # Partial match - check if extracted term contains or is contained in mapping terms
        if not matches:
            for instrument, entries in self.instrument_lookup.items():
                if instrument in extracted_term or extracted_term in instrument:
                    for entry in entries:
                        if entry not in matches:
                            matches.append(entry)
            if matches:
                logger.debug(f"✅ Partial match found: {len(matches)} entries")
        
        # Word-based matching (for cases like "Pfandbriefe" matching "Pfandbrief")
        if not matches:
            extracted_words = set(re.findall(r'\w+', extracted_term))
            for instrument, entries in self.instrument_lookup.items():
                instrument_words = set(re.findall(r'\w+', instrument))
                # If significant overlap in words
                if len(extracted_words & instrument_words) >= min(2, len(extracted_words), len(instrument_words)):
                    for entry in entries:
                        if entry not in matches:
                            matches.append(entry)
            if matches:
                logger.debug(f"✅ Word-based match found: {len(matches)} entries")
        
        if not matches:
            logger.warning(f"⚠️ No matches found for '{extracted_term}'. Available entries: {list(self.instrument_lookup.keys())[:10]}...")
        
        return matches
    
    def get_all_entries(self) -> List[Dict]:
        """Get all mapping entries"""
        return self.mapping_data
    
    def update_allowed_status(self, row_id: int, allowed: bool, reason: str = "") -> None:
        """
        Update the allowed status for a specific entry.
        
        Args:
            row_id: Excel row number (1-indexed)
            allowed: Whether investment is allowed
            reason: Reason/evidence for the decision
        """
        for entry in self.mapping_data:
            if entry['row_id'] == row_id:
                entry['allowed'] = allowed
                entry['reason'] = reason
                break
    
    def update_entry_by_instrument(self, instrument: str, allowed: bool, reason: str = "") -> None:
        """
        Update allowed status for all entries matching an instrument.
        
        Args:
            instrument: Instrument/category name
            allowed: Whether investment is allowed
            reason: Reason/evidence for the decision
        """
        matches = self.find_matching_entries(instrument)
        for entry in matches:
            entry['allowed'] = allowed
            entry['reason'] = reason
    
    def detect_negative_logic(self, text: str, term: str) -> Tuple[bool, str]:
        """
        Detect negative logic in text.
        Example: "abc funds are permitted" means NOT allowed (negative logic).
        
        Args:
            text: Full text or context snippet
            term: The term being analyzed
        
        Returns:
            Tuple of (is_negative, explanation)
        """
        text_lower = text.lower()
        term_lower = term.lower()
        
        # Patterns that indicate negative logic
        negative_patterns = [
            r'not\s+(?:permitted|allowed|authorized|approved)',
            r'prohibited|forbidden|restricted|excluded|banned',
            r'cannot|may\s+not|shall\s+not',
            r'except|excluding|unless',
        ]
        
        # Patterns that indicate positive logic
        positive_patterns = [
            r'(?:permitted|allowed|authorized|approved)',
            r'may\s+invest|can\s+invest',
            r'investments?\s+(?:are|is)\s+(?:permitted|allowed)',
        ]
        
        # Check for negative patterns near the term
        term_pos = text_lower.find(term_lower)
        if term_pos != -1:
            # Extract context around the term (100 chars before and after)
            start = max(0, term_pos - 100)
            end = min(len(text_lower), term_pos + len(term_lower) + 100)
            context = text_lower[start:end]
            
            # Check for negative logic
            for pattern in negative_patterns:
                if re.search(pattern, context):
                    return True, f"Negative logic detected: {pattern}"
            
            # Check for positive logic
            for pattern in positive_patterns:
                if re.search(pattern, context):
                    return False, f"Positive logic detected: {pattern}"
        
        # Default: no negative logic detected
        return False, "No negative logic detected"
    
    def export_to_excel(self, output_path: str) -> str:
        """
        Export ALL mapping data with filled ticks to Excel file.
        This exports all 137 entries, regardless of whether they were matched.
        
        Args:
            output_path: Path to save the Excel file
        
        Returns:
            Path to saved Excel file
        """
        try:
            # Create DataFrame from ALL mapping data (all 137 entries)
            df_data = []
            total_entries = len(self.mapping_data)
            processed_count = 0
            
            for entry in self.mapping_data:
                # Determine allowed status
                allowed_status = entry.get('allowed')
                if allowed_status is True:
                    allowed_display = '✓'
                    processed_count += 1
                elif allowed_status is False:
                    allowed_display = '✗'  # Show X for explicitly prohibited
                    processed_count += 1
                else:
                    allowed_display = ''  # Empty if not found or uncertain
                
                df_data.append({
                    'Instrument/Category': entry['instrument_category'],
                    'hint/notice': entry['hint_notice'],
                    'Asset Tree Type1': entry['asset_tree_type1'],
                    'Asset Tree Type2': entry['asset_tree_type2'],
                    'Asset Tree Type3': entry['asset_tree_type3'],
                    'restriction': entry['restriction'],
                    'allowed': allowed_display,
                    'reason': entry.get('reason', '')
                })
            
            df = pd.DataFrame(df_data)
            
            logger.info(f"EXCEL EXPORT: Exporting {total_entries} total entries ({processed_count} processed, {total_entries - processed_count} unprocessed)")
            
            if total_entries != 137:
                logger.warning(f"Expected 137 entries but found {total_entries}. Make sure you've loaded the full Excel file!")
            
            # Write to Excel with formatting
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Mapping Results', index=False)
                
                # Get the worksheet for formatting
                worksheet = writer.sheets['Mapping Results']
                
                # Style headers
                from openpyxl.styles import PatternFill, Font, Alignment
                header_fill = PatternFill(start_color="FF8C00", end_color="FF8C00", fill_type="solid")
                white_font = Font(color="FFFFFF", bold=True)
                
                for cell in worksheet[1]:
                    cell.fill = header_fill
                    cell.font = white_font
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                
                # Auto-adjust column widths
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 80)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
            
            logger.info(f"Exported mapping results to: {output_path}")
            return output_path
            
        except Exception as e:
            raise Exception(f"Failed to export Excel: {str(e)}")
    
    async def search_document_with_llm(self, document_text: str, llm_service, llm_provider: str, model: str) -> Dict:
        """
        Search document for ALL Excel entries (Column A terms) and use LLM to determine if allowed/prohibited.
        For each term found, extracts context and asks LLM to determine if it's allowed or not.
        
        Args:
            document_text: Full text of the document to search
            llm_service: LLMService instance for analysis
            llm_provider: LLM provider name
            model: Model name to use
        
        Returns:
            Dictionary with statistics about matches found
        """
        document_lower = document_text.lower()
        matches_found = 0
        allowed_found = 0
        prohibited_found = 0
        
        logger.info(f"🔍 Searching document for {len(self.mapping_data)} Excel entries using LLM analysis...")
        
        for entry in self.mapping_data:
            instrument_name = entry['instrument_category'].strip()
            if not instrument_name or instrument_name == 'nan':
                continue
            
            # Search for instrument name in document (case-insensitive)
            instrument_lower = instrument_name.lower()
            instrument_words = set(re.findall(r'\w+', instrument_lower))
            
            # Find all positions where instrument name appears
            found_positions = []
            
            # First try exact match
            start_pos = 0
            while True:
                pos = document_lower.find(instrument_lower, start_pos)
                if pos == -1:
                    break
                found_positions.append(pos)
                start_pos = pos + 1
            
            # If no exact match, try word-based matching
            if not found_positions and instrument_words:
                for word in instrument_words:
                    if len(word) >= 4:  # Only search for significant words (4+ chars)
                        word_positions = []
                        start = 0
                        while True:
                            pos = document_lower.find(word, start)
                            if pos == -1:
                                break
                            word_positions.append(pos)
                            start = pos + 1
                        
                        # Check if other words are nearby
                        for wp in word_positions:
                            nearby_words = 0
                            for other_word in instrument_words:
                                if other_word != word and len(other_word) >= 4:
                                    check_start = max(0, wp - 50)
                                    check_end = min(len(document_lower), wp + len(word) + 50)
                                    if other_word in document_lower[check_start:check_end]:
                                        nearby_words += 1
                            
                            if nearby_words > 0 or len(instrument_words) == 1:
                                found_positions.append(wp)
                                break
                        
                        if found_positions:
                            break
            
            if found_positions:
                matches_found += 1
                
                # Extract context around the first occurrence (use larger context for LLM)
                pos = found_positions[0]
                context_start = max(0, pos - 500)
                context_end = min(len(document_text), pos + len(instrument_name) + 500)
                context = document_text[context_start:context_end]
                
                # Use LLM to analyze if this term is allowed or prohibited
                try:
                    import json
                    
                    llm_prompt = f"""You are analyzing an investment policy document. The term "{instrument_name}" appears in the context below.

Determine if "{instrument_name}" is ALLOWED or PROHIBITED based on the context.

Context:
{context}

Respond with ONLY a JSON object (no other text):
{{
  "allowed": true or false,
  "reason": "brief explanation"
}}

Rules:
- If context says "permitted", "allowed", "authorized", "may invest", "can invest" → "allowed": true
- If context says "prohibited", "forbidden", "not allowed", "restricted", "excluded" → "allowed": false
- If context is unclear or just mentions the term without permission/restriction → "allowed": false"""
                    
                    # Call LLM to analyze using analyze_text method
                    llm_response = await llm_service.analyze_text(llm_prompt)
                    
                    # Parse LLM response
                    if isinstance(llm_response, dict):
                        if "error" in llm_response:
                            error_msg = llm_response.get("error", "Unknown LLM error")
                            logger.warning(f"LLM error for '{instrument_name}': {error_msg}")
                            entry['allowed'] = None
                            entry['reason'] = f"LLM error: {error_msg}"
                        elif "allowed" in llm_response:
                            # Direct response with allowed key
                            allowed = bool(llm_response.get("allowed", False))
                            reason = llm_response.get("reason", "LLM analysis")
                            entry['allowed'] = allowed
                            entry['reason'] = f"LLM: {reason}"
                            
                            if allowed:
                                allowed_found += 1
                                logger.debug(f"✅ LLM: '{instrument_name}' = ALLOWED")
                            else:
                                prohibited_found += 1
                                logger.debug(f"❌ LLM: '{instrument_name}' = PROHIBITED")
                        else:
                            # Try to extract JSON from response text
                            response_text = json.dumps(llm_response) if not isinstance(llm_response, str) else llm_response
                            json_start = response_text.find('{')
                            json_end = response_text.rfind('}') + 1
                            if json_start != -1 and json_end > json_start:
                                try:
                                    json_str = response_text[json_start:json_end]
                                    parsed = json.loads(json_str)
                                    allowed = bool(parsed.get("allowed", False))
                                    reason = parsed.get("reason", "LLM analysis")
                                    entry['allowed'] = allowed
                                    entry['reason'] = f"LLM: {reason}"
                                    
                                    if allowed:
                                        allowed_found += 1
                                    else:
                                        prohibited_found += 1
                                except json.JSONDecodeError:
                                    entry['allowed'] = None
                                    entry['reason'] = "LLM response JSON parse failed"
                            else:
                                entry['allowed'] = None
                                entry['reason'] = "LLM response format invalid"
                    else:
                        entry['allowed'] = None
                        entry['reason'] = "LLM returned invalid response type"
                        
                except Exception as e:
                    logger.error(f"Error calling LLM for '{instrument_name}': {e}", exc_info=True)
                    entry['allowed'] = None
                    entry['reason'] = f"LLM error: {str(e)}"
            else:
                # Not found in document - leave as None (will show as empty in Excel)
                entry['allowed'] = None
                entry['reason'] = "Not found in document"
        
        logger.info(f"✅ LLM analysis complete: {matches_found} entries found, {allowed_found} allowed, {prohibited_found} prohibited")
        
        return {
            'total_entries': len(self.mapping_data),
            'matches_found': matches_found,
            'allowed_found': allowed_found,
            'prohibited_found': prohibited_found,
            'not_found': len(self.mapping_data) - matches_found
        }
    
    def search_document_for_all_entries(self, document_text: str) -> Dict:
        """
        Search document text for ALL Excel entries and mark them as allowed/permitted.
        This searches the document directly for each instrument name and checks context.
        
        Args:
            document_text: Full text of the document to search
            
        Returns:
            Dictionary with statistics about matches found
        """
        document_lower = document_text.lower()
        matches_found = 0
        allowed_found = 0
        
        logger.info(f"🔍 Searching document for {len(self.mapping_data)} Excel entries...")
        
        for entry in self.mapping_data:
            instrument_name = entry['instrument_category'].strip()
            if not instrument_name or instrument_name == 'nan':
                continue
            
            # Search for instrument name in document (case-insensitive)
            instrument_lower = instrument_name.lower()
            instrument_words = set(re.findall(r'\w+', instrument_lower))
            
            # Find all positions where instrument name appears (exact or word-based)
            found_positions = []
            
            # First try exact match
            start_pos = 0
            while True:
                pos = document_lower.find(instrument_lower, start_pos)
                if pos == -1:
                    break
                found_positions.append(pos)
                start_pos = pos + 1
            
            # If no exact match, try word-based matching
            if not found_positions and instrument_words:
                # Find positions where key words appear close together
                for word in instrument_words:
                    if len(word) >= 4:  # Only search for significant words (4+ chars)
                        word_positions = []
                        start = 0
                        while True:
                            pos = document_lower.find(word, start)
                            if pos == -1:
                                break
                            word_positions.append(pos)
                            start = pos + 1
                        
                        # If we found this word, check if other words are nearby (within 50 chars)
                        for wp in word_positions:
                            # Check if other instrument words appear nearby
                            nearby_words = 0
                            for other_word in instrument_words:
                                if other_word != word and len(other_word) >= 4:
                                    # Check if other word appears within 50 chars
                                    check_start = max(0, wp - 50)
                                    check_end = min(len(document_lower), wp + len(word) + 50)
                                    if other_word in document_lower[check_start:check_end]:
                                        nearby_words += 1
                            
                            # If at least one other word is nearby, consider it a match
                            if nearby_words > 0 or len(instrument_words) == 1:
                                found_positions.append(wp)
                                break
                        
                        if found_positions:
                            logger.debug(f"Found '{instrument_name}' via word-based matching (word: '{word}')")
                            break
            
            if found_positions:
                matches_found += 1
                
                # Find all occurrences and check context for "allowed/permitted"
                found_allowed = False
                found_prohibited = False
                evidence_text = ""
                
                # Check context for each found position
                for pos in found_positions:
                    
                    # Extract context around the match (200 chars before and after)
                    # Use instrument_lower length for exact matches, or estimate for word matches
                    match_length = len(instrument_lower) if pos != -1 else 20
                    context_start = max(0, pos - 200)
                    context_end = min(len(document_lower), pos + match_length + 200)
                    context = document_lower[context_start:context_end]
                    
                    # Check for allowed/permitted keywords in context
                    allowed_keywords = ['allowed', 'permitted', 'authorized', 'approved', 'may invest', 'can invest']
                    prohibited_keywords = ['prohibited', 'forbidden', 'not allowed', 'restricted', 'excluded', 'may not invest', 'cannot invest']
                    
                    # Check if any allowed keyword appears before prohibited keywords
                    allowed_positions = [context.find(kw) for kw in allowed_keywords if context.find(kw) != -1]
                    prohibited_positions = [context.find(kw) for kw in prohibited_keywords if context.find(kw) != -1]
                    
                    # If allowed keywords found and no prohibited keywords, or allowed is closer
                    if allowed_positions:
                        if not prohibited_positions or min(allowed_positions) < min(prohibited_positions):
                            found_allowed = True
                            # Extract the sentence or phrase containing the match
                            sentence_start = max(0, context.find('.', max(0, pos - context_start - 100)))
                            sentence_end = context.find('.', pos - context_start + len(instrument_lower) + 100)
                            if sentence_end == -1:
                                sentence_end = len(context)
                            evidence_text = context[sentence_start:sentence_end].strip()
                            break
                    
                    # If prohibited keywords found
                    if prohibited_positions:
                        found_prohibited = True
                        sentence_start = max(0, context.find('.', max(0, pos - context_start - 100)))
                        sentence_end = context.find('.', pos - context_start + len(instrument_lower) + 100)
                        if sentence_end == -1:
                            sentence_end = len(context)
                        evidence_text = context[sentence_start:sentence_end].strip()
                        break  # Found prohibited, no need to check more positions
                
                # Mark entry based on what was found
                if found_allowed:
                    entry['allowed'] = True
                    entry['reason'] = f"Found in document with 'allowed/permitted' context: {evidence_text[:200]}"
                    allowed_found += 1
                    logger.debug(f"✅ Found '{instrument_name}' as ALLOWED in document")
                elif found_prohibited:
                    entry['allowed'] = False
                    entry['reason'] = f"Found in document with 'prohibited/restricted' context: {evidence_text[:200]}"
                    logger.debug(f"❌ Found '{instrument_name}' as PROHIBITED in document")
                else:
                    # Found in document but unclear context - mark as found but uncertain
                    entry['allowed'] = None  # Keep as None to indicate found but uncertain
                    entry['reason'] = f"Found in document but context unclear: {evidence_text[:200] if evidence_text else 'No clear permission/restriction found'}"
                    logger.debug(f"⚠️ Found '{instrument_name}' in document but context unclear")
            else:
                # Not found in document - leave as None (will show as empty in Excel)
                entry['allowed'] = None
                entry['reason'] = "Not found in document"
        
        logger.info(f"✅ Document search complete: {matches_found} entries found, {allowed_found} marked as allowed")
        
        return {
            'total_entries': len(self.mapping_data),
            'matches_found': matches_found,
            'allowed_found': allowed_found,
            'not_found': len(self.mapping_data) - matches_found
        }
    
    def get_statistics(self) -> Dict:
        """Get statistics about the mapping data"""
        total = len(self.mapping_data)
        allowed = sum(1 for e in self.mapping_data if e.get('allowed') is True)
        not_allowed = sum(1 for e in self.mapping_data if e.get('allowed') is False)
        unset = total - allowed - not_allowed
        
        return {
            'total_entries': total,
            'allowed': allowed,
            'not_allowed': not_allowed,
            'unset': unset,
            'coverage': (allowed + not_allowed) / total * 100 if total > 0 else 0
        }

