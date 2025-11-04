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
            
            print(f"Loaded {len(self.mapping_data)} entries from Excel file: {excel_path}")
            
        except Exception as e:
            print(f"Error loading Excel file: {e}")
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
            print(f"Excel mapping loaded from embedded code: {len(self.mapping_data)} entries")
        except ImportError:
            # Fallback: empty mapping if embedded file doesn't exist
            self.mapping_data = []
            self._build_lookup_indexes()
            print("Excel mapping loaded from code (empty - run load_excel_mapping.py to populate)")
    
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
        
        # Direct match
        if extracted_term in self.instrument_lookup:
            matches.extend(self.instrument_lookup[extracted_term])
        
        # Partial match - check if extracted term contains or is contained in mapping terms
        for instrument, entries in self.instrument_lookup.items():
            if instrument in extracted_term or extracted_term in instrument:
                for entry in entries:
                    if entry not in matches:
                        matches.append(entry)
        
        # Word-based matching (for cases like "Pfandbriefe" matching "Pfandbrief")
        extracted_words = set(re.findall(r'\w+', extracted_term))
        for instrument, entries in self.instrument_lookup.items():
            instrument_words = set(re.findall(r'\w+', instrument))
            # If significant overlap in words
            if len(extracted_words & instrument_words) >= min(2, len(extracted_words), len(instrument_words)):
                for entry in entries:
                    if entry not in matches:
                        matches.append(entry)
        
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
                    allowed_display = ''
                    processed_count += 1
                else:
                    allowed_display = ''  # Empty if not processed
                
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
            
            print(f"[EXCEL EXPORT] Exporting {total_entries} total entries ({processed_count} processed, {total_entries - processed_count} unprocessed)")
            
            if total_entries != 137:
                print(f"[WARNING] Expected 137 entries but found {total_entries}. Make sure you've loaded the full Excel file!")
            
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
            
            print(f"Exported mapping results to: {output_path}")
            return output_path
            
        except Exception as e:
            raise Exception(f"Failed to export Excel: {str(e)}")
    
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

