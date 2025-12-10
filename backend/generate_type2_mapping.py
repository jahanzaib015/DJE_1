"""
Generate Type2 to OCRD schema mapping from Investment_Mapping.xlsx
"""
import pandas as pd
import os

excel_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Investment_Mapping.xlsx")
df = pd.read_excel(excel_path)

# OCRD schema names (from analysis_service.py)
ocrd_schema = {
    "bond": ["covered_bond", "asset_backed_security", "mortgage_bond", "pfandbrief", "public_mortgage_bond", 
             "convertible_bond_regular", "convertible_bond_coco", "reverse_convertible", "credit_linked_note", 
             "commercial_paper", "genussscheine_bondlike", "inflation_linked", "participation_paper", 
             "plain_vanilla_bond", "promissory_note", "warrant_linked_bond"],
    "stock": ["common_stock", "depositary_receipt", "genussschein_stocklike", "partizipationsschein", 
              "preferred_stock", "reit", "right"],
    "fund": ["alternative_investment_fund", "commodity_fund", "equity_fund", "fixed_income_fund", 
             "mixed_allocation_fund", "moneymarket_fund", "private_equity_fund", "real_estate_fund", "speciality_fund"],
    "deposit": ["call_money", "cash", "time_deposit"],
    "future": ["bond_future", "commodity_future", "currency_future", "fund_future", "index_future", "single_stock_future"],
    "option": ["bond_future_option", "commodity_future_option", "commodity_option", "currency_future_option", 
               "currency_option", "fund_future_option", "fund_option", "index_future_option", "index_option", "stock_option"],
    "warrant": ["commodity_warrant", "currency_warrant", "fund_warrant", "index_warrant", "stock_warrant"],
    "commodity": ["precious_metal"],
    "forex": ["forex_outright", "forex_spot"],
    "swap": ["credit_default_swap", "interest_swap", "total_return_swap"],
}

# Build mapping from Excel Type2/Type3 to OCRD schema names
type2_to_ocrd = {}

for _, row in df.iterrows():
    type1 = str(row.get('Asset Tree Type1', '')).strip().lower()
    type2 = str(row.get('Asset Tree Type2', '')).strip().lower()
    type3 = str(row.get('Asset Tree Type3', '')).strip().lower()
    
    if type1 and type1 in ocrd_schema:
        section_keys = ocrd_schema[type1]
        
        # Handle Type2
        if type2 and type2 != 'nan':
            # Normalize type2 (replace spaces with underscores, handle special cases)
            type2_normalized = type2.replace(" ", "_")
            
            # Try to find matching OCRD key
            for key in section_keys:
                key_normalized = key.replace("_", " ").lower()
                if type2 in key_normalized or key_normalized in type2:
                    type2_to_ocrd[type2] = key
                    break
                elif type2_normalized in key or key in type2_normalized:
                    type2_to_ocrd[type2] = key
                    break
        
        # Handle Type3 (can contain multiple comma-separated values)
        if type3 and type3 != 'nan':
            type3_parts = [p.strip().lower() for p in type3.split(',')]
            for part in type3_parts:
                part_normalized = part.replace(" ", "_")
                for key in section_keys:
                    key_normalized = key.replace("_", " ").lower()
                    if part in key_normalized or key_normalized in part:
                        type2_to_ocrd[part] = key
                        break
                    elif part_normalized in key or key in part_normalized:
                        type2_to_ocrd[part] = key
                        break

# Print the mapping
print("Type2 to OCRD Schema Mapping:")
print("=" * 60)
for type2, ocrd_key in sorted(type2_to_ocrd.items()):
    print(f'    "{type2}": "{ocrd_key}",')

print(f"\nTotal mappings: {len(type2_to_ocrd)}")





