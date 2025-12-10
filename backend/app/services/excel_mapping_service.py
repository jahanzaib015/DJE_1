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
from difflib import get_close_matches
from ..utils.logger import setup_logger

logger = setup_logger(__name__)

# =========================
# NEW: Guardrails & Helpers
# =========================
GENERIC_PARENTS = {
    "bond", "bonds", "equity", "equities", "stock", "stocks",
    "derivative", "derivatives", "fund", "funds",
    "security", "securities", "fixed income", "debt instrument", "debt instruments"
}
ALLOW_MARKERS = re.compile(r"\b(eligible|permitted|allowed|authorized|approved|may invest|can invest|investment universe includes)\b", re.I)
PROHIBIT_MARKERS = re.compile(r"\b(prohibited|forbidden|not allowed|not permitted|restricted|excluded|shall not|may not|cannot)\b", re.I)
CONDITIONAL_MARKERS = re.compile(r"\b(subject to|provided that|unless|up to|limit|capped at|conditional)\b", re.I)
ALL_QUANTIFIERS = re.compile(r"\b(all|any|in general|including but not limited to)\b", re.I)

def _normalize_simple(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def _is_generic_parent(term: str) -> bool:
    return _normalize_simple(term) in GENERIC_PARENTS

def _sentence_window(text: str, pos: int, span: int = 260) -> str:
    start = max(0, pos - span)
    end = min(len(text), pos + span)
    return text[start:end]


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
        self.synonym_lookup: Dict[str, List[Dict]] = {}  # normalized synonym -> entries
        self._indexes_built = False  # Lazy loading flag
        
        logger.debug(f"Initializing ExcelMappingService with path: {excel_path}")
        
        if excel_path:
            if os.path.exists(excel_path):
                logger.info(f"Loading Excel file: {excel_path}")
                self.load_from_excel(excel_path)
            else:
                logger.debug(f"Excel file not found at: {excel_path}, using embedded mapping")
                self._load_from_code()
        else:
            logger.debug("No Excel path provided, loading from embedded code...")
            self._load_from_code()
        
        logger.info(f"ExcelMappingService initialized with {len(self.mapping_data)} entries")
    
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
            logger.info(f"Reading Excel file: {excel_path}")
            df = pd.read_excel(excel_path, sheet_name=0, header=0)
            logger.info(f"Excel file read: {len(df)} rows, {len(df.columns)} columns")
            
            required_columns = ['Instrument/Category', 'hint/notice', 'Asset Tree Type1', 
                              'Asset Tree Type2', 'Asset Tree Type3', 'restriction']
            
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
            
            self.mapping_data = []
            rows_processed = 0
            rows_skipped = 0
            for idx, row in df.iterrows():
                entry = {
                    'row_id': idx + 2,  # Excel row number (header row = 1)
                    'instrument_category': str(row.get('Instrument/Category', '')).strip(),
                    'hint_notice': str(row.get('hint/notice', '')).strip(),
                    'asset_tree_type1': str(row.get('Asset Tree Type1', '')).strip(),
                    'asset_tree_type2': str(row.get('Asset Tree Type2', '')).strip(),
                    'asset_tree_type3': str(row.get('Asset Tree Type3', '')).strip(),
                    'restriction': str(row.get('restriction', '')).strip(),
                    'allowed': None  # Will be filled during analysis
                }
                if not entry['instrument_category'] or entry['instrument_category'] == 'nan':
                    rows_skipped += 1
                    continue
                self.mapping_data.append(entry)
                rows_processed += 1
            
            logger.info(f"Processed {rows_processed} valid entries, skipped {rows_skipped} empty rows")
            # Don't build indexes immediately - build them lazily when first needed
            self._indexes_built = False
            
            logger.info(f"Successfully loaded {len(self.mapping_data)} entries from Excel file")
            logger.info("Lookup indexes will be built on first use")
            
        except Exception as e:
            logger.error(f"Error loading Excel file: {e}", exc_info=True)
            raise Exception(f"Failed to load Excel mapping file: {str(e)}")
    
    def _load_from_code(self) -> None:
        """
        Load mapping data from embedded code structure.
        This will be populated from the Excel file you provide.
        """
        try:
            from ..utils.embedded_mapping import MAPPING_DATA
            self.mapping_data = MAPPING_DATA
            self._indexes_built = False  # Build indexes lazily
            logger.info(f"Excel mapping loaded from embedded code: {len(self.mapping_data)} entries")
            if len(self.mapping_data) == 0:
                logger.warning("Embedded mapping data is empty! Run load_excel_mapping.py to populate.")
        except ImportError as e:
            self.mapping_data = []
            self._indexes_built = False
            logger.warning(f"Could not import embedded mapping: {e}")
            logger.warning("Excel mapping is empty - run load_excel_mapping.py to populate")
        except Exception as e:
            logger.error(f"Error loading embedded mapping: {e}")
            self.mapping_data = []
            self._indexes_built = False
    
    def _normalize_term(self, value: str) -> str:
        """Normalize a text value for fuzzy matching"""
        if not value:
            return ""
        value = value.lower().strip()
        value = value.replace("_", " ").replace("-", " ")
        value = re.sub(r"[^a-z0-9\s]", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def _add_synonym(self, synonym: str, entry: Dict) -> None:
        """Helper to register a synonym mapping"""
        synonym = self._normalize_term(synonym)
        if not synonym or len(synonym) < 3:
            return
        if synonym not in self.synonym_lookup:
            self.synonym_lookup[synonym] = []
        if entry not in self.synonym_lookup[synonym]:
            self.synonym_lookup[synonym].append(entry)

    def _extract_candidate_synonyms(self, entry: Dict) -> List[str]:
        """Generate potential synonym strings for an entry"""
        candidates: List[str] = []
        fields = [
            entry.get('instrument_category', ''),
            entry.get('hint_notice', ''),
            entry.get('asset_tree_type1', ''),
            entry.get('asset_tree_type2', ''),
            entry.get('asset_tree_type3', ''),
            entry.get('restriction', '')
        ]
        for field in fields:
            if not field or field == 'nan':
                continue
            parts = re.split(r"[,/;]|\band\b|\border\b|\bsowie\b|\n", field, flags=re.IGNORECASE)
            for part in parts:
                part = part.strip()
                if part:
                    candidates.append(part)
                    if part.endswith('s') and len(part) > 4:
                        candidates.append(part[:-1])
                    elif len(part) > 4:
                        candidates.append(f"{part}s")
        return candidates

    def _build_lookup_indexes(self) -> None:
        """Build fast lookup indexes for matching (lazy - only builds once)"""
        if self._indexes_built:
            return  # Already built
        
        logger.debug("Building lookup indexes...")
        self.instrument_lookup = {}
        self.asset_tree_lookup = {}
        self.synonym_lookup = {}

        for entry in self.mapping_data:
            instrument = entry['instrument_category'].lower().strip()

            if instrument:
                if instrument not in self.instrument_lookup:
                    self.instrument_lookup[instrument] = []
                self.instrument_lookup[instrument].append(entry)
                self._add_synonym(instrument, entry)

                words = re.findall(r'\w+', instrument)
                for word in words:
                    if len(word) > 3:
                        if word not in self.instrument_lookup:
                            self.instrument_lookup[word] = []
                        if entry not in self.instrument_lookup[word]:
                            self.instrument_lookup[word].append(entry)
                        self._add_synonym(word, entry)

            for candidate in self._extract_candidate_synonyms(entry):
                self._add_synonym(candidate, entry)

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
                        if 'default' not in self.asset_tree_lookup[type1][type2]:
                            self.asset_tree_lookup[type1][type2]['default'] = []
                        self.asset_tree_lookup[type1][type2]['default'].append(entry)
                else:
                    if 'default' not in self.asset_tree_lookup[type1]:
                        self.asset_tree_lookup[type1]['default'] = {}
                    if 'default' not in self.asset_tree_lookup[type1]['default']:
                        self.asset_tree_lookup[type1]['default']['default'] = []
                    self.asset_tree_lookup[type1]['default']['default'].append(entry)
        
        self._indexes_built = True
        logger.debug("Lookup indexes built")
    
    def find_matching_entries(self, extracted_term: str, context: Optional[str] = None) -> List[Dict]:
        """Find matching entries - builds indexes if not already built"""
        if not self._indexes_built:
            self._build_lookup_indexes()
        """
        Find matching entries for an extracted term from PDF.
        Conservative filter: prefer specific over generic; avoid generic-only matches.
        """
        extracted_term = extracted_term.lower().strip()
        matches = []
        normalized = self._normalize_term(extracted_term)

        logger.info(f"🔍 Searching for matches for: '{extracted_term}' (lookup has {len(self.instrument_lookup)} entries)")

        if extracted_term in self.instrument_lookup:
            matches.extend(self.instrument_lookup[extracted_term])
            logger.info(f"✅ Direct match found: {len(matches)} entries")
        
        if not matches:
            for instrument, entries in self.instrument_lookup.items():
                if instrument in extracted_term or extracted_term in instrument:
                    for entry in entries:
                        if entry not in matches:
                            matches.append(entry)
            if matches:
                logger.info(f"✅ Partial match found: {len(matches)} entries")
        
        if not matches:
            extracted_words = set(re.findall(r'\w+', extracted_term))
            for instrument, entries in self.instrument_lookup.items():
                instrument_words = set(re.findall(r'\w+', instrument))
                if len(extracted_words & instrument_words) >= min(2, len(extracted_words), len(instrument_words)):
                    for entry in entries:
                        if entry not in matches:
                            matches.append(entry)
            if matches:
                logger.info(f"✅ Word-based match found: {len(matches)} entries")
        
        if not matches and normalized:
            # Only log warning if Excel mapping has data (to reduce noise when empty)
            if len(self.instrument_lookup) > 0:
                logger.debug(f"⚠️ No matches found for '{extracted_term}'.")
            if normalized in self.synonym_lookup:
                for entry in self.synonym_lookup[normalized]:
                    if entry not in matches:
                        matches.append(entry)
            if not matches:
                synonym_keys = list(self.synonym_lookup.keys())
                close = get_close_matches(normalized, synonym_keys, n=5, cutoff=0.75)
                for key in close:
                    for entry in self.synonym_lookup.get(key, []):
                        if entry not in matches:
                            matches.append(entry)
                if close:
                    logger.info(f"✅ Fuzzy synonym match for '{extracted_term}' -> {close}")

        # --- NEW: prefer specific matches over generic parents ---
        if matches:
            exact = [e for e in matches if _normalize_simple(e['instrument_category']) == _normalize_simple(extracted_term)]
            if exact:
                matches = exact
            else:
                non_generic = [e for e in matches if not _is_generic_parent(e['instrument_category'])]
                if non_generic:
                    matches = non_generic

        if not matches and normalized:
            # Only log warning if Excel mapping has data (to reduce noise when empty)
            if len(self.instrument_lookup) > 0:
                logger.debug(f"⚠️ Still no matches after fuzzy search for '{extracted_term}' (normalized='{normalized}')")

        return matches
    
    def get_all_entries(self) -> List[Dict]:
        """Get all mapping data"""
        return self.mapping_data
    
    def get_term_map(self) -> Dict[str, Dict]:
        """Get term map - builds indexes if not already built"""
        if not self._indexes_built:
            self._build_lookup_indexes()
        """
        Build a term_map dictionary for conservative classification.
        
        Returns:
            Dict mapping term -> {"primary": bool, "specificity": int, "parent": str}
            where:
            - primary: True if this is a primary instrument category (not a synonym)
            - specificity: Higher number = more specific (e.g., "covered bond" = 3, "bond" = 1)
            - parent: Parent category if applicable (e.g., "bond" for "covered bond")
        """
        term_map = {}
        
        # Build term map from all entries
        for entry in self.mapping_data:
            instrument_category = entry.get('instrument_category', '').strip()
            if not instrument_category:
                continue
            
            # Determine specificity based on how specific the term is
            # More words = more specific (e.g., "covered bond" = 2, "bond" = 1)
            words = instrument_category.split()
            specificity = len(words)
            
            # Check if this is a generic parent term
            is_generic = _is_generic_parent(instrument_category)
            
            # Determine parent category from asset tree
            parent = None
            type1 = entry.get('asset_tree_type1', '').strip().lower()
            type2 = entry.get('asset_tree_type2', '').strip().lower()
            
            # If we have type2, type1 is the parent
            if type2:
                parent = type1
            # If we only have type1 and it's generic, it might be a parent
            elif type1 and is_generic:
                parent = None  # Generic terms are usually top-level
            
            # Add to term_map
            term_map[instrument_category] = {
                "primary": True,  # All entries are primary
                "specificity": specificity,
                "parent": parent
            }
            
            # Also add normalized version for matching
            normalized = _normalize_simple(instrument_category)
            if normalized != instrument_category.lower():
                term_map[normalized] = {
                    "primary": False,  # Normalized version is not primary
                    "specificity": specificity,
                    "parent": parent
                }
        
        return term_map
    
    def update_allowed_status(self, row_id: int, allowed: bool, reason: str = "") -> None:
        """Update the allowed status for a specific entry."""
        for entry in self.mapping_data:
            if entry['row_id'] == row_id:
                entry['allowed'] = allowed
                entry['reason'] = reason
                break
    
    def update_entry_by_instrument(self, instrument: str, allowed: bool, reason: str = "") -> None:
        """
        STRICT: Only update rows whose Instrument/Category equals the instrument (case-insensitive).
        Prevents accidental bulk updates from fuzzy matches.
        """
        needle = _normalize_simple(instrument)
        for entry in self.mapping_data:
            if _normalize_simple(entry.get('instrument_category')) == needle:
                entry['allowed'] = allowed
                entry['reason'] = reason
    
    def detect_negative_logic(self, text: str, term: str) -> Tuple[bool, str]:
        """
        Detect negative logic in text. (Kept for backward compatibility)
        IMPORTANT: This should NOT flip logic for items in "Zulässige Anlagen" sections.
        """
        text_lower = (text or "").lower()
        term_lower = (term or "").lower()
        
        # CRITICAL: Check for German section headers FIRST - these override negative logic detection
        # If the text contains "Zulässige Anlagen" (Permitted Investments), it's positive logic
        german_positive_sections = [
            r'zulässige\s+anlagen',
            r'zulässige\s+anlageinstrumente',
            r'erlaubt|zugelassen|berechtigt|darf',
            r'ja\s*[,\|:]',  # "ja" followed by comma, pipe, or colon (list format)
        ]
        
        # Check if we're in a positive German section
        for pattern in german_positive_sections:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return False, f"Positive German section detected: {pattern} - DO NOT flip logic"
        
        # Check for German prohibited sections
        german_negative_sections = [
            r'unzulässige\s+anlagen',
            r'unzulässige\s+anlageinstrumente',
            r'verboten|nicht\s+erlaubt|ausgeschlossen|darf\s+nicht',
            r'nein\s*[,\|:]',  # "nein" followed by comma, pipe, or colon (list format)
        ]
        
        for pattern in german_negative_sections:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True, f"Negative German section detected: {pattern}"
        
        negative_patterns = [
            r'not\s+(?:permitted|allowed|authorized|approved)',
            r'prohibited|forbidden|restricted|excluded|banned',
            r'cannot|may\s+not|shall\s+not',
            r'except|excluding|unless',
        ]
        positive_patterns = [
            r'(?:permitted|allowed|authorized|approved)',
            r'may\s+invest|can\s+invest',
            r'investments?\s+(?:are|is)\s+(?:permitted|allowed)',
        ]
        term_pos = text_lower.find(term_lower)
        if term_pos != -1:
            start = max(0, term_pos - 200)  # Increased context window
            end = min(len(text_lower), term_pos + len(term_lower) + 200)
            context = text_lower[start:end]
            
            # Check for positive patterns FIRST (they override negative)
            for pattern in positive_patterns:
                if re.search(pattern, context):
                    return False, f"Positive logic detected: {pattern}"
            
            # Then check for negative patterns
            for pattern in negative_patterns:
                if re.search(pattern, context):
                    return True, f"Negative logic detected: {pattern}"
        return False, "No negative logic detected"
    
    def export_to_excel(self, output_path: str) -> str:
        """
        Export ALL mapping data with filled ticks to Excel file.
        """
        try:
            df_data = []
            total_entries = len(self.mapping_data)
            processed_count = 0
            
            for entry in self.mapping_data:
                allowed_status = entry.get('allowed')
                if allowed_status is True:
                    allowed_display = '✓'
                    status_display = 'Allowed'
                    processed_count += 1
                elif allowed_status is False:
                    allowed_display = '✗'
                    status_display = 'Prohibited'
                    processed_count += 1
                else:
                    allowed_display = ''
                    status_display = 'Review'
                
                df_data.append({
                    'Instrument/Category': entry['instrument_category'],
                    'hint/notice': entry['hint_notice'],
                    'Asset Tree Type1': entry['asset_tree_type1'],
                    'Asset Tree Type2': entry['asset_tree_type2'],
                    'Asset Tree Type3': entry['asset_tree_type3'],
                    'restriction': entry['restriction'],
                    'allowed': allowed_display,
                    'status': status_display,   # NEW
                    'reason': entry.get('reason', '')
                })
            
            df = pd.DataFrame(df_data)
            logger.info(f"EXCEL EXPORT: Exporting {total_entries} total entries ({processed_count} processed, {total_entries - processed_count} unprocessed)")
            
            if total_entries != 137:
                logger.warning(f"Expected 137 entries but found {total_entries}. Make sure you've loaded the full Excel file!")
            
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Mapping Results', index=False)
                from openpyxl.styles import PatternFill, Font, Alignment
                worksheet = writer.sheets['Mapping Results']
                header_fill = PatternFill(start_color="FF8C00", end_color="FF8C00", fill_type="solid")
                white_font = Font(color="FFFFFF", bold=True)
                for cell in worksheet[1]:
                    cell.fill = header_fill
                    cell.font = white_font
                    cell.alignment = Alignment(horizontal="center", vertical="center")
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
        Search document for ALL Excel entries (Column A terms) using LLM with OCRD IDs and semantic matching.
        DEMO-SAFE: conservative defaults, explicit evidence only, no parent roll-up without quantifier.
        """
        matches_found = 0
        allowed_found = 0
        prohibited_found = 0
        
        logger.info(f"🔍 Searching document for {len(self.mapping_data)} Excel entries using LLM semantic analysis...")
        
        ocrd_taxonomy = {
            "bond": ["covered_bond", "asset_backed_security", "mortgage_bond", "pfandbrief", "public_mortgage_bond", 
                    "convertible_bond_regular", "convertible_bond_coco", "reverse_convertible", "credit_linked_note", 
                    "commercial_paper", "genussscheine_bondlike", "inflation_linked", "participation_paper", 
                    "plain_vanilla_bond", "promissory_note", "warrant_linked_bond"],
            "certificate": ["bond_certificate", "commodity_certificate", "currency_certificate", "fund_certificate", 
                           "index_certificate", "stock_certificate"],
            "stock": ["common_stock", "depositary_receipt", "genussschein_stocklike", "partizipationsschein", 
                     "preferred_stock", "reit", "right"],
            "fund": ["alternative_investment_fund", "commodity_fund", "equity_fund", "fixed_income_fund", 
                    "mixed_allocation_fund", "moneymarket_fund", "private_equity_fund", "real_estate_fund", "speciality_fund"],
            "deposit": ["call_money", "cash", "time_deposit"],
            "future": ["bond_future", "commodity_future", "currency_future", "fund_future", "index_future", "single_stock_future"],
            "option": ["bond_future_option", "commodity_future_option", "commodity_option", 
                      "currency_future_option", "currency_option", "fund_future_option", "fund_option", 
                      "index_future_option", "index_option", "stock_option"],
            "warrant": ["commodity_warrant", "currency_warrant", "fund_warrant", "index_warrant", "stock_warrant"],
            "commodity": ["precious_metal"],
            "forex": ["forex_outright", "forex_spot"],
            "swap": ["credit_default_swap", "interest_swap", "total_return_swap"],
            "loan": [],
            "private_equity": [],
            "real_estate": [],
            "rights": ["subscription_rights"]
        }
        all_ocrd_ids = []
        for category, ids in ocrd_taxonomy.items():
            all_ocrd_ids.extend([f"{category}.{id}" for id in ids])
            if not ids:
                all_ocrd_ids.append(category)
        ocrd_ids_text = "\n".join([f"- {id}" for id in all_ocrd_ids[:50]])

        for entry_idx, entry in enumerate(self.mapping_data, 1):
            instrument_name = entry['instrument_category'].strip()
            if not instrument_name or instrument_name == 'nan':
                continue
            
            logger.info(f"🔍 [{entry_idx}/{len(self.mapping_data)}] Analyzing: '{instrument_name}'")
            type1 = entry.get('asset_tree_type1', '').strip()
            type2 = entry.get('asset_tree_type2', '').strip()
            type3 = entry.get('asset_tree_type3', '').strip()
            ocrd_ids_for_entry = []
            if type1: ocrd_ids_for_entry.append(type1)
            if type2 and type2 != 'nan':
                ocrd_ids_for_entry.append(f"{type1}.{type2}" if type1 else type2)
            if type3 and type3 != 'nan':
                for part in [p.strip() for p in type3.split(',')]:
                    if part and part != 'nan':
                        ocrd_ids_for_entry.append(part)
            ocrd_ids_str = ", ".join(ocrd_ids_for_entry) if ocrd_ids_for_entry else "N/A"
            logger.info(f"   📋 OCRD IDs to check: {ocrd_ids_str}")
            
            try:
                import json
                max_chunk_size = 200000
                if len(document_text) > max_chunk_size:
                    chunk_size = max_chunk_size
                    overlap = 5000
                    document_chunks = []
                    start = 0
                    while start < len(document_text):
                        end = min(start + chunk_size, len(document_text))
                        document_chunks.append(document_text[start:end])
                        start = end - overlap
                    logger.info(f"   📄 Document split into {len(document_chunks)} chunks (total size: {len(document_text)} chars)")
                else:
                    document_chunks = [document_text]
                    logger.info(f"   📄 Processing document as single chunk ({len(document_text)} chars)")
                
                found_in_document = False
                allowed_status = None
                reason_text = ""
                semantic_match = instrument_name
                ocrd_match = "N/A"
                
                for chunk_idx, chunk in enumerate(document_chunks):
                    logger.info(f"   Checking chunk {chunk_idx + 1}/{len(document_chunks)} (size: {len(chunk)} chars)")
                    try:
                        # Add timeout for each LLM call to prevent hanging
                        llm_prompt = f"""You are classifying whether a specific instrument is ALLOWED or PROHIBITED in an investment policy document. Your PRIMARY goal is to find ALLOWED items - they are just as important as prohibited ones.

**CRITICAL: PRIORITIZE FINDING ALLOWED ITEMS FIRST**
Your first priority is to actively search for and identify when this instrument is ALLOWED. Many documents have comprehensive lists of allowed instruments - you must find them.

**STEP 1: SEARCH FOR ALLOWED EVIDENCE (HIGHEST PRIORITY)**
Actively look for these patterns that indicate the instrument is ALLOWED. **THE MOST COMMON PATTERN IS "Ja/yes" IN TABLES:**

**PRIMARY INDICATOR: "Ja/yes" = ALLOWED (allowed=true)**
- **CRITICAL**: If you see "{instrument_name}" followed by "Ja/yes", "Ja / yes", "Ja/ yes", "Ja /yes", or just "Ja" or "yes" → it is ALLOWED (allowed=true)
- **CRITICAL**: If you see "{instrument_name}" in a table row where the "Ja/yes" column is marked → it is ALLOWED (allowed=true)
- **CRITICAL**: Even if table structure is broken, if "{instrument_name}" appears near "Ja/yes", "Ja", "yes", "ja", or "erlaubt" → it is ALLOWED (allowed=true)
- **CRITICAL**: Format variations to recognize: "Ja/yes", "Ja / yes", "Ja/ yes", "Ja /yes", "Ja", "yes", "ja" (all mean ALLOWED)
- Examples: "Staatsanleihen / Government Bonds: Ja/yes" → ALLOWED
- Examples: "Covered Bonds / Covered Bonds: Ja/yes" → ALLOWED
- Examples: "Aktienfonds / Equity-Funds: Ja/yes" → ALLOWED
- Examples: "Delta-1 Zertifikate / Delta-1 Certificates: Ja/yes" → ALLOWED
- Examples: "Corporate Bonds: Ja" → ALLOWED
- Examples: "Financial-Anleihen: yes" → ALLOWED

**OTHER ALLOWED PATTERNS:**
- "allowed", "permitted", "authorized", "approved", "may invest", "can invest", "eligible"
- German: "erlaubt", "zugelassen", "berechtigt", "darf", "zulässig"
- German: "erlaubt/allowed" (bilingual format) → ALLOWED
- An "X" (cross) mark in ANY context - tables, lists, inline text, checkboxes
- "FX Forwards are allowed", "currency futures are permitted", "forex is authorized"
- Lists of permitted instruments (especially under "Zulässige Anlagen")
- Positive statements: "investments are permitted in...", "the fund may invest in...", "investments in X are allowed"
- **MOST IMPORTANT**: If the instrument appears in a "Zulässige Anlagen" (Permitted Investments) section → it is ALLOWED

**STEP 2: THEN SEARCH FOR PROHIBITED EVIDENCE**
Look for these patterns that indicate the instrument is PROHIBITED:
- "prohibited", "forbidden", "not allowed", "restricted", "excluded", "may not invest", "not eligible"
- German: "verboten", "nicht erlaubt", "ausgeschlossen", "darf nicht", "nein", "unzulässig"
- A "-" (hyphen/dash) mark in ANY context
- "investments in X are not allowed", "prohibited from investing in..."
- **MOST IMPORTANT**: If the instrument appears in an "Unzulässige Anlagen" (Prohibited Investments) section → it is PROHIBITED

**CRITICAL: GERMAN TABLE FORMAT (HIGHEST PRIORITY - MOST COMMON FORMAT)**
Many German investment documents use tables with "Ja/yes" and "nein/no" classifications. This is THE PRIMARY format for identifying allowed/prohibited status.

**TABLE FORMAT RECOGNITION:**
- Look for tables with columns or classifications: "Ja/yes", "nein/no", "Relevant", "Detailrestriktionen"
- Table may appear as: "Instrument Name | nein/no | Ja/yes | Detailrestriktionen"
- Or in text format: "Staatsanleihen / Government Bonds: Ja/yes"
- Or as a list: "Aktien: nein/no, Covered Bonds: Ja/yes"
- Or in structured format: "Instrument Name" followed by "Ja/yes" or "nein/no" in the same row
- **CRITICAL**: Even if the table structure is broken in text extraction, look for patterns like:
  * "{instrument_name}" followed by "Ja/yes" or "Ja / yes" → ALLOWED
  * "{instrument_name}" followed by "nein/no" or "nein / no" → NOT ALLOWED
  * "{instrument_name}" with "Ja/yes" anywhere in the same sentence/row → ALLOWED
  * Rows where you can identify "Ja/yes" or "nein/no" classifications

**INTERPRETATION RULES FOR TABLES (APPLY TO EACH ROW):**
- **CRITICAL RULE #1**: "Ja/yes" or "Ja / yes" next to instrument name = ALLOWED (allowed=true) - THIS IS THE MOST IMPORTANT RULE
- **CRITICAL RULE #2**: "X" (cross) in "ja" column = ALLOWED (allowed=true) - SECOND MOST IMPORTANT
- "nein/no" or "nein / no" next to instrument name = NOT ALLOWED (allowed=false)
- "X" (cross) in "nein" column = NOT ALLOWED (allowed=false)
- "✓" (checkmark) in "ja" column = ALLOWED (allowed=true)
- "-" (hyphen/dash) in either column = typically NOT ALLOWED
- **MOST IMPORTANT**: If you see "{instrument_name}" followed by "Ja/yes" → that instrument is ALLOWED (allowed=true)
- **MOST IMPORTANT**: If you see "{instrument_name}" in a table row with "ja: X" or "X" in the "ja" column position → that instrument is ALLOWED (allowed=true)

**OTHER GERMAN PATTERNS:**
- **"Ja/yes" or "Ja / yes" = ALLOWED (allowed=true)** - This is the most common pattern in German investment documents
- **"nein/no" or "nein / no" = NOT ALLOWED (allowed=false)**
- "ja" = yes/allowed, "nein" = no/not allowed
- German keywords: "erlaubt", "zugelassen", "berechtigt", "darf" = allowed/permitted
- German keywords: "erlaubt/allowed" (bilingual) = allowed/permitted
- German keywords: "verboten", "nicht erlaubt", "ausgeschlossen", "darf nicht" = prohibited/not allowed
- German keywords: "nicht erlaubt/not allowed" (bilingual) = prohibited/not allowed
- Examples in text: "FX Forwards X", "Derivatives (X)", "Options: -", "Bonds -", "Aktien ✓"
- Examples in tables: "Staatsanleihen: Ja/yes" → ALLOWED, "Swaptions: nein/no" → NOT ALLOWED
- When you see X or - marks in any context, interpret "X" as allowed=true and "-" as allowed=false

**CRITICAL: GERMAN SECTION HEADERS WITH LISTS**
- When you see "Zulässige Anlagen" or "Zulässige Anlageinstrumente" section → ALL items in that list are allowed=true
- When you see "Unzulässige Anlagen" or "Unzulässige Anlageinstrumente" section → ALL items in that list are allowed=false
- If the instrument you're checking appears in one of these sections, classify it accordingly
- These lists can be formatted as bullet points, numbered lists, comma-separated items, or table rows
- **VERIFICATION**: Count the items and ensure you check all of them

**INSTRUMENT TO CHECK:**
"{instrument_name}"

**OCRD IDs (semantic categories) to consider:**
{ocrd_ids_str}

**CLASSIFICATION RULES:**
1. Work at the SENTENCE, BULLET, or TABLE ROW level
2. **CRITICAL**: If you find "{instrument_name}" (or a semantic match) followed by "Ja/yes" in the same row/sentence → set "allowed": true
3. **CRITICAL**: If you find "{instrument_name}" (or a semantic match) followed by "nein/no" in the same row/sentence → set "allowed": false
4. If you find explicit evidence the instrument is ALLOWED (any pattern) → set "allowed": true
5. If you find explicit evidence the instrument is PROHIBITED (any pattern) → set "allowed": false
6. If the sentence is conditional (e.g., "subject to", "up to", "provided that") → still set allowed=true but include condition in reason
7. If you find the instrument mentioned but cannot determine allowed/prohibited status → set "found": true but omit "allowed" key
8. **IMPORTANT**: Do NOT infer from broader categories - only classify if the SPECIFIC instrument is mentioned
9. **IMPORTANT**: For generic parent categories (bonds, equities, derivatives), only classify as allowed if the sentence explicitly includes "all", "any", or "including but not limited to"
10. **SEMANTIC MATCHING**: If "{instrument_name}" doesn't appear exactly but a related term appears with "Ja/yes", consider it a match (e.g., "Government Bonds: Ja/yes" matches "government_bond" or "sovereign_bond")
11. **CRITICAL: PARENT CATEGORIES VS SUBTYPES**: If you see a parent category (e.g., "Bonds", "Renten") marked as "Ja/yes", you MUST still check each subtype separately. A parent category being allowed does NOT mean all subtypes are allowed. Check the table for subtype rows - if a subtype shows "nein/no", it is NOT ALLOWED regardless of parent category status.

**EXAMPLES (REAL DOCUMENT PATTERNS):**
- If document says "{instrument_name} / {{english_name}}: Ja/yes" → {{"found": true, "allowed": true, "reason": "{instrument_name}: Ja/yes"}}
- If document says "{instrument_name}: Ja/yes" → {{"found": true, "allowed": true, "reason": "{instrument_name}: Ja/yes"}}
- If document says "{instrument_name} / {{english_name}}: nein/no" → {{"found": true, "allowed": false, "reason": "{instrument_name}: nein/no"}}
- If document says "{instrument_name} X" or "{instrument_name} | ja: X" → {{"found": true, "allowed": true, "reason": "{instrument_name} X (in ja column)"}}
- If document says "{instrument_name} are allowed" or "{instrument_name}: erlaubt/allowed" → {{"found": true, "allowed": true, "reason": "{instrument_name} are allowed"}}
- If document says "{instrument_name} are prohibited" or "{instrument_name}: nicht erlaubt/not allowed" → {{"found": true, "allowed": false, "reason": "{instrument_name} are prohibited"}}
- If document says "{instrument_name}" in "Zulässige Anlagen" section → {{"found": true, "allowed": true, "reason": "Listed in Zulässige Anlagen section"}}
- If document says "{instrument_name}" in "Unzulässige Anlagen" section → {{"found": true, "allowed": false, "reason": "Listed in Unzulässige Anlagen section"}}
- **CRITICAL EXAMPLE**: If you see "Staatsanleihen / Government Bonds: Ja/yes" and you're checking "Government Bonds" → {{"found": true, "allowed": true, "reason": "Staatsanleihen / Government Bonds: Ja/yes"}}

**OCRD Taxonomy (subset):**
{ocrd_ids_text}

**Document excerpt to search:**
{chunk[:200000]}

**YOUR TASK:**
1. **FIRST AND MOST IMPORTANT**: Search for "{instrument_name}" followed by "Ja/yes" or "Ja / yes" - this is the PRIMARY indicator of ALLOWED status
2. Search for "{instrument_name}" in tables with "Ja/yes" classifications - these are ALLOWED
3. Search for "{instrument_name}" with X marks in "ja" columns - these are ALLOWED
4. Search for "{instrument_name}" in "Zulässige Anlagen" sections - these are ALLOWED
5. Search for other positive language patterns (allowed, permitted, erlaubt, etc.)
6. **THEN**: Search for "{instrument_name}" followed by "nein/no" - this indicates NOT ALLOWED
7. Search for "{instrument_name}" in "Unzulässige Anlagen" sections - these are NOT ALLOWED
8. Search for other negative language patterns (prohibited, verboten, etc.)
9. If you find the instrument mentioned but cannot determine status, still set "found": true
10. **CRITICAL**: Use exact quotes from the document as evidence in the "reason" field - include the "Ja/yes" or "nein/no" classification if present

Respond with ONLY a JSON object:
{{
  "found": true or false,
  "semantic_match": "exact phrase that matched (if found)",
  "ocrd_match": "OCRD ID/category if applicable or 'N/A'",
  "allowed": true or false (include this key ONLY if you found explicit allowed/prohibited evidence),
  "reason": "exact quote or evidence from document (verbatim copy, max 300 chars)"
}}"""
                        prompt_preview = llm_prompt[:500] + "..." if len(llm_prompt) > 500 else llm_prompt
                        logger.info(f"   Sending prompt to LLM (length: {len(llm_prompt)} chars)")
                        logger.debug(f"   Prompt preview: {prompt_preview}")
                        
                        # Add timeout to prevent hanging (30 seconds per chunk)
                        import asyncio
                        llm_response = await asyncio.wait_for(
                            llm_service.analyze_text(llm_prompt),
                            timeout=30.0
                        )
                        logger.info(f"   LLM Response received (type: {type(llm_response).__name__})")
                        
                        if isinstance(llm_response, dict):
                            logger.debug(f"   Response keys: {list(llm_response.keys())}")
                            
                            if "error" in llm_response:
                                logger.warning(f"   LLM error in chunk {chunk_idx + 1}: {llm_response.get('error')}")
                                continue
                            elif llm_response.get("found") is True:
                                found_in_document = True
                                semantic_match = llm_response.get("semantic_match", instrument_name)
                                ocrd_match = llm_response.get("ocrd_match", "N/A")
                                if "allowed" in llm_response:
                                    allowed_status = bool(llm_response.get("allowed", False))
                                    reason_text = llm_response.get("reason", f"Found semantically as: {semantic_match}")
                                    if ocrd_match and ocrd_match != "N/A":
                                        reason_text += f" (OCRD: {ocrd_match})"
                                    break
                                else:
                                    reason_text = llm_response.get("reason", f"Found semantically as: {semantic_match}; evidence inconclusive")
                            else:
                                logger.debug(f"   Not found in chunk {chunk_idx + 1}, continuing...")
                        else:
                            response_text = json.dumps(llm_response) if not isinstance(llm_response, str) else llm_response
                            json_start = response_text.find('{')
                            json_end = response_text.rfind('}') + 1
                            if json_start != -1 and json_end > json_start:
                                try:
                                    parsed = json.loads(response_text[json_start:json_end])
                                    if parsed.get("found") is True:
                                        found_in_document = True
                                        semantic_match = parsed.get("semantic_match", instrument_name)
                                        ocrd_match = parsed.get("ocrd_match", "N/A")
                                        if "allowed" in parsed:
                                            allowed_status = bool(parsed.get("allowed", False))
                                            reason_text = parsed.get("reason", f"Found semantically as: {semantic_match}")
                                            if ocrd_match and ocrd_match != "N/A":
                                                reason_text += f" (OCRD: {ocrd_match})"
                                            break
                                        else:
                                            reason_text = parsed.get("reason", f"Found semantically as: {semantic_match}; evidence inconclusive")
                                except Exception as e:
                                    logger.warning(f"   Failed to parse JSON from response: {e}")
                                    pass
                    except asyncio.TimeoutError:
                        logger.warning(f"   LLM call timed out for chunk {chunk_idx + 1} - skipping")
                        continue
                    except Exception as e:
                        logger.warning(f"   Error in LLM call for chunk {chunk_idx + 1}: {e}")
                        continue
                
                if found_in_document:
                    matches_found += 1
                    if allowed_status is not None:
                        entry['allowed'] = allowed_status
                        entry['reason'] = f"LLM semantic match: {reason_text}"
                        if allowed_status:
                            allowed_found += 1
                            logger.info(f"   ✅ '{instrument_name}' = ALLOWED ✓")
                        else:
                            prohibited_found += 1
                            logger.info(f"   ❌ '{instrument_name}' = PROHIBITED ✗")
                    else:
                        entry['allowed'] = None
                        entry['reason'] = f"Found semantically but permission status unclear: {reason_text}"
                        logger.warning(f"   ⚠️ '{instrument_name}': Found but permission status unclear")
                else:
                    entry['allowed'] = None
                    entry['reason'] = "Not found in document (semantic search)"
                    logger.info(f"   ❌ '{instrument_name}': NOT FOUND in document after semantic search")
                        
            except Exception as e:
                logger.error(f"Error calling LLM for '{instrument_name}': {e}", exc_info=True)
                entry['allowed'] = None
                entry['reason'] = f"LLM error: {str(e)}"
        
        logger.info("=" * 80)
        logger.info(f"✅ LLM SEMANTIC ANALYSIS COMPLETE")
        logger.info(f"   📊 Total entries processed: {len(self.mapping_data)}")
        logger.info(f"   ✅ Found in document: {matches_found}")
        logger.info(f"   ✓ Allowed: {allowed_found}")
        logger.info(f"   ✗ Prohibited: {prohibited_found}")
        logger.info(f"   ❌ Not found: {len(self.mapping_data) - matches_found}")
        logger.info("=" * 80)
        
        return {
            'total_entries': len(self.mapping_data),
            'matches_found': matches_found,
            'allowed_found': allowed_found,
            'prohibited_found': prohibited_found,
            'not_found': len(self.mapping_data) - matches_found
        }
    
    def search_document_for_all_entries(self, document_text: str) -> Dict:
        """
        Deterministic scan: sentence-level evidence, no parent promotion without ALL/ANY.
        """
        document_lower = (document_text or "").lower()
        matches_found = 0
        allowed_found = 0
        
        logger.info(f"🔍 Searching document for {len(self.mapping_data)} Excel entries...")
        
        for entry in self.mapping_data:
            instrument_name = entry['instrument_category'].strip()
            if not instrument_name or instrument_name == 'nan':
                continue
            
            instrument_lower = instrument_name.lower()
            instrument_words = set(re.findall(r'\w+', instrument_lower))
            found_positions = []
            
            # exact
            start_pos = 0
            while True:
                pos = document_lower.find(instrument_lower, start_pos)
                if pos == -1:
                    break
                found_positions.append(pos)
                start_pos = pos + 1
            
            # word-based
            if not found_positions and instrument_words:
                for word in instrument_words:
                    if len(word) >= 4:
                        start = 0
                        while True:
                            pos = document_lower.find(word, start)
                            if pos == -1:
                                break
                            # quick vicinity check for another word
                            check_start = max(0, pos - 50)
                            check_end = min(len(document_lower), pos + len(word) + 50)
                            nearby_ok = any(
                                (other != word and len(other) >= 4 and other in document_lower[check_start:check_end])
                                for other in instrument_words
                            )
                            if nearby_ok or len(instrument_words) == 1:
                                found_positions.append(pos)
                                break
                            start = pos + 1
                        if found_positions:
                            logger.debug(f"Found '{instrument_name}' via word-based matching (word: '{word}')")
                            break
            
            if found_positions:
                matches_found += 1
                found_label = None  # "Allowed" | "Prohibited" | "Conditional" | None
                evidence_text = ""
                
                for pos in found_positions:
                    ctx = _sentence_window(document_lower, pos, span=260)
                    term_present = instrument_lower in ctx
                    has_neg = bool(PROHIBIT_MARKERS.search(ctx))
                    has_allow = bool(ALLOW_MARKERS.search(ctx))
                    has_cond = bool(CONDITIONAL_MARKERS.search(ctx))
                    if _is_generic_parent(instrument_name):
                        has_all_quant = bool(ALL_QUANTIFIERS.search(ctx))
                    else:
                        has_all_quant = True

                    if term_present:
                        if has_neg:
                            found_label = "Prohibited"
                            evidence_text = ctx.strip()
                            break
                        if has_allow and has_all_quant:
                            found_label = "Conditional" if has_cond else "Allowed"
                            evidence_text = ctx.strip()
                        elif has_allow and not has_all_quant and _is_generic_parent(instrument_name):
                            # don't promote generic parent without quantifier
                            pass
                        elif has_cond and has_all_quant:
                            found_label = found_label or "Conditional"
                            evidence_text = evidence_text or ctx.strip()
                
                if found_label == "Allowed":
                    entry['allowed'] = True
                    entry['reason'] = f"Evidence: {evidence_text[:300]}"
                    allowed_found += 1
                    logger.debug(f"✅ Found '{instrument_name}' as ALLOWED in document")
                elif found_label == "Prohibited":
                    entry['allowed'] = False
                    entry['reason'] = f"Evidence: {evidence_text[:300]}"
                    logger.debug(f"❌ Found '{instrument_name}' as PROHIBITED in document")
                elif found_label == "Conditional":
                    entry['allowed'] = None
                    entry['reason'] = f"Conditional/limited: {evidence_text[:300]}"
                    logger.debug(f"⚠️ '{instrument_name}' conditional")
                else:
                    entry['allowed'] = None
                    entry['reason'] = "Found, but no explicit allow/prohibit sentence in context"
                    logger.debug(f"⚠️ '{instrument_name}' found but inconclusive")
            else:
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
