# Excel Mapping System

This system uses an Excel mapping table to standardize and match financial instrument terms extracted from PDF documents.

## Overview

The Excel mapping system provides:
1. **Standardized Taxonomy**: Maps PDF terms to your standard instrument/category names
2. **Hierarchical Classification**: Asset Tree Type1 → Type2 → Type3 structure
3. **Negative Logic Detection**: Handles cases like "abc funds are permitted" (meaning NOT allowed)
4. **Automatic Matching**: Matches extracted terms to Excel entries
5. **Filled Excel Export**: Outputs Excel with ticks marking allowed/not allowed

## Excel File Structure

Your Excel file should have these columns:

| Column | Description | Example |
|--------|-------------|---------|
| A: Instrument/Category | Terms found in PDFs | "Pfandbriefe", "Investment funds" |
| B: hint/notice | Additional notes | "no OPUS Assetclass" |
| C: Asset Tree Type1 | Base asset type | "bond", "stock", "fund" |
| D: Asset Tree Type2 | Sub-classification | "covered_bond", "equity_fund" |
| E: Asset Tree Type3 | Further detail | "mortgage_bond", "regular convertible" |
| F: restriction | Specific restrictions | "Masterdata/Subordination=true" |
| G: allowed | Tick column (filled by system) | ✓ or empty |

## Setup Instructions

### Step 1: Prepare Your Excel File

Ensure your Excel file has all 137 entries with the correct column structure.

### Step 2: Generate Embedded Code

Run the utility script to convert Excel to Python code:

```bash
cd backend
python app/utils/load_excel_mapping.py <path_to_your_excel.xlsx> app/utils/embedded_mapping.py
```

This will:
- Load all 137 entries from your Excel
- Generate Python code with embedded data
- Save it to `backend/app/utils/embedded_mapping.py`

### Step 3: Verify

The system will automatically load the embedded mapping on startup. Check logs for:
```
Excel mapping loaded from embedded code: 137 entries
```

## How It Works

### 1. PDF Analysis Flow

```
PDF Upload → Text Extraction → OpenAI LLM → Extract Rules → Excel Mapping → Fill Ticks → Export
```

### 2. Term Matching

When OpenAI extracts an instrument term (e.g., "Pfandbriefe"), the system:
1. Searches Excel mapping for matching entries
2. Handles variations (e.g., "Pfandbrief" matches "Pfandbriefe")
3. Uses word-based matching for partial matches

### 3. Negative Logic Detection

The system detects negative logic in context:
- **Pattern**: "abc funds are permitted" = NOT allowed
- **Detection**: Checks for negative patterns near the term
- **Action**: Flips the `allowed` flag if negative logic detected

### 4. Excel Export

After analysis, the system:
- Fills the "allowed" column (Column G) with ✓ for allowed, empty for not allowed
- Includes reason/evidence in a separate column
- Exports the filled Excel file

## API Endpoints

### Export Mapping Results

```http
GET /api/jobs/{job_id}/export/mapping
```

Returns the filled Excel mapping table with ticks.

## Usage in Code

### Initialize with Excel File (Optional)

```python
from app.services.excel_mapping_service import ExcelMappingService

# Load from Excel file (for development)
mapping = ExcelMappingService(excel_path="path/to/mapping.xlsx")

# Or use embedded code (production)
mapping = ExcelMappingService()
```

### Find Matching Entries

```python
matches = mapping.find_matching_entries("Pfandbriefe", context=full_text)
for entry in matches:
    print(f"Found: {entry['instrument_category']} -> {entry['asset_tree_type1']}")
```

### Update Allowed Status

```python
mapping.update_allowed_status(row_id=5, allowed=True, reason="Document states...")
```

### Export Filled Excel

```python
mapping.export_to_excel("output.xlsx")
```

## Negative Logic Examples

The system handles various negative logic patterns:

| Pattern | Meaning |
|---------|---------|
| "abc funds are permitted" | NOT allowed (negative logic) |
| "investments in X are not allowed" | NOT allowed (explicit) |
| "prohibited from investing in Y" | NOT allowed (explicit) |
| "investments in Z are allowed" | Allowed (positive) |

## Troubleshooting

### No entries loaded

**Problem**: "Excel mapping loaded from code (empty - needs Excel file)"

**Solution**: Run the load script:
```bash
python backend/app/utils/load_excel_mapping.py your_excel.xlsx backend/app/utils/embedded_mapping.py
```

### Terms not matching

**Problem**: Extracted terms don't match Excel entries

**Solution**: 
- Check spelling variations in Excel
- Add synonyms/aliases to Excel
- The system uses fuzzy matching, but exact matches are preferred

### Negative logic not detected

**Problem**: "abc funds are permitted" still marked as allowed

**Solution**: 
- Ensure full text context is passed (system uses full PDF text)
- Check negative pattern detection in `excel_mapping_service.py`
- Add custom patterns if needed

## File Structure

```
backend/
├── app/
│   ├── services/
│   │   └── excel_mapping_service.py    # Main mapping service
│   └── utils/
│       ├── load_excel_mapping.py        # Utility to convert Excel to code
│       └── embedded_mapping.py          # Embedded mapping data (generated)
└── EXCEL_MAPPING_README.md              # This file
```

## Notes

- The Excel file is converted to Python code for performance
- All 137 entries are embedded in the codebase
- No Excel file needed at runtime (only PDF uploads)
- The system still uses OpenAI APIs for extraction
- Excel mapping improves accuracy and standardization

