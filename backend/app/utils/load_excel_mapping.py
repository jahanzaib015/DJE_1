"""
Utility script to load Excel mapping and generate Python code for embedding.
Run this once to convert Excel file to Python data structure.
"""
import pandas as pd
import os
from pathlib import Path


def load_excel_to_code(excel_path: str, output_file: str = None) -> str:
    """
    Load Excel mapping file and generate Python code with embedded data.
    
    Args:
        excel_path: Path to Excel file
        output_file: Optional path to save generated Python code
    
    Returns:
        Python code as string
    """
    # Read Excel file
    df = pd.read_excel(excel_path, sheet_name=0, header=0)
    
    # Generate Python code
    code_lines = [
        "# Auto-generated mapping data from Excel file",
        "# This file contains all 137 instrument/category mapping entries",
        "# DO NOT EDIT MANUALLY - regenerate from Excel using load_excel_mapping.py",
        "",
        "MAPPING_DATA = ["
    ]
    
    row_id = 2  # Excel row number (assuming header at row 1)
    for idx, row in df.iterrows():
        # Get values, handling NaN
        instrument = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        hint_notice = str(row.iloc[1]).strip() if len(row) > 1 and pd.notna(row.iloc[1]) else ""
        type1 = str(row.iloc[2]).strip() if len(row) > 2 and pd.notna(row.iloc[2]) else ""
        type2 = str(row.iloc[3]).strip() if len(row) > 3 and pd.notna(row.iloc[3]) else ""
        type3 = str(row.iloc[4]).strip() if len(row) > 4 and pd.notna(row.iloc[4]) else ""
        restriction = str(row.iloc[5]).strip() if len(row) > 5 and pd.notna(row.iloc[5]) else ""
        
        # Skip empty rows
        if not instrument or instrument == 'nan':
            continue
        
        # Escape strings properly
        def escape_string(s):
            if not s or s == 'nan':
                return '""'
            return repr(s)
        
        code_lines.append(f"    {{")
        code_lines.append(f"        'row_id': {row_id},")
        code_lines.append(f"        'instrument_category': {escape_string(instrument)},")
        code_lines.append(f"        'hint_notice': {escape_string(hint_notice)},")
        code_lines.append(f"        'asset_tree_type1': {escape_string(type1)},")
        code_lines.append(f"        'asset_tree_type2': {escape_string(type2)},")
        code_lines.append(f"        'asset_tree_type3': {escape_string(type3)},")
        code_lines.append(f"        'restriction': {escape_string(restriction)},")
        code_lines.append(f"        'allowed': None,")
        code_lines.append(f"    }},")
        
        row_id += 1
    
    code_lines.append("]")
    
    code = "\n".join(code_lines)
    
    # Save to file if specified
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(code)
        print(f"Generated Python code with {row_id - 2} entries saved to: {output_file}")
    else:
        print(f"Generated Python code with {row_id - 2} entries")
    
    return code


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python load_excel_mapping.py <excel_file_path> [output_file.py]")
        print("\nExample:")
        print("  python load_excel_mapping.py mapping.xlsx")
        print("  python load_excel_mapping.py mapping.xlsx embedded_mapping.py")
        sys.exit(1)
    
    excel_path = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not os.path.exists(excel_path):
        print(f"Error: Excel file not found: {excel_path}")
        sys.exit(1)
    
    code = load_excel_to_code(excel_path, output_file)
    
    if not output_file:
        print("\n" + "="*80)
        print("Generated Python code:")
        print("="*80)
        print(code)

