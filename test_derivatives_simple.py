"""
Simple diagnostic test - logs to file for debugging
"""
import json
import sys
import os

# Test document
TEST_DOCUMENT = """The fund may invest in equity options and index futures. Warrants may also be used for hedging."""

print("=" * 80, file=sys.stderr)
print("DERIVATIVES DIAGNOSTIC TEST", file=sys.stderr)
print("=" * 80, file=sys.stderr)
print(f"\nTest Document:\n{TEST_DOCUMENT}\n", file=sys.stderr)

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

try:
    print("Importing modules...", file=sys.stderr)
    from app.services.analysis_service import AnalysisService
    from app.services.llm_service import LLMService
    print("Imports successful", file=sys.stderr)
    
    # Initialize
    print("Initializing services...", file=sys.stderr)
    llm_service = LLMService()
    analysis_service = AnalysisService(llm_service=llm_service)
    
    print("\n" + "=" * 80, file=sys.stderr)
    print("STEP 1: Getting raw LLM response...", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    
    import asyncio
    
    async def run_test():
        # Get raw LLM response
        raw_response = await llm_service.analyze_document(
            TEST_DOCUMENT,
            "openai",
            "gpt-4o-mini"
        )
        
        print("\n✅ Raw LLM Response:", file=sys.stderr)
        print(json.dumps(raw_response, indent=2, ensure_ascii=False), file=sys.stderr)
        
        # Check instrument rules
        instrument_rules = raw_response.get("instrument_rules", [])
        print(f"\n📊 Total instrument rules: {len(instrument_rules)}", file=sys.stderr)
        
        derivatives_rules = [
            r for r in instrument_rules
            if any(term in str(r.get("instrument", "")).lower() 
                   for term in ["derivative", "future", "option", "warrant"])
        ]
        
        print(f"🔍 Derivatives-related rules: {len(derivatives_rules)}", file=sys.stderr)
        for rule in derivatives_rules:
            print(f"  - {rule.get('instrument')}: allowed={rule.get('allowed')}, reason='{rule.get('reason', '')[:80]}...'", file=sys.stderr)
        
        # Convert to OCRD
        print("\n" + "=" * 80, file=sys.stderr)
        print("STEP 2: Converting to OCRD format...", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        
        converted = analysis_service._convert_llm_response_to_ocrd_format(raw_response, full_text=TEST_DOCUMENT)
        
        # Check derivatives
        derivative_section = converted.get("sections", {}).get("derivative", {})
        
        print("\n📋 Final Derivative Results:", file=sys.stderr)
        for subtype in ["future", "option", "warrant"]:
            if subtype in derivative_section:
                subtype_data = derivative_section[subtype]
                instruments = {k: v for k, v in subtype_data.items() 
                              if k != "special_other_restrictions" and isinstance(v, dict)}
                
                allowed = sum(1 for v in instruments.values() if v.get("allowed") is True)
                prohibited = sum(1 for v in instruments.values() if v.get("allowed") is False)
                undetermined = sum(1 for v in instruments.values() if v.get("allowed") is None)
                
                print(f"\n{subtype.upper()}:", file=sys.stderr)
                print(f"  Allowed: {allowed}, Prohibited: {prohibited}, Undetermined: {undetermined}", file=sys.stderr)
                
                # Show first instrument
                if instruments:
                    first_key = list(instruments.keys())[0]
                    first_val = instruments[first_key]
                    print(f"  Sample ({first_key}): allowed={first_val.get('allowed')}, evidence='{first_val.get('evidence', {}).get('text', '')[:80]}...'", file=sys.stderr)
    
    asyncio.run(run_test())
    
except Exception as e:
    print(f"\n❌ Error: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)





