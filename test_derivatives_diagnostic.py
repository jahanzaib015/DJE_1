"""
Diagnostic test for derivatives issue.
Tests a minimal document and logs raw LLM response vs final processed result.
"""
import asyncio
import json
import sys
import os

print("Starting diagnostic test script...", flush=True)

# Add backend to path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)
print(f"Added backend path: {backend_path}", flush=True)

try:
    from app.services.analysis_service import AnalysisService
    from app.services.llm_service import LLMService
    from app.models.analysis_models import LLMProvider
    from app.utils.logger import setup_logger
    print("Imports successful", flush=True)
except ImportError as e:
    print(f"Import error: {e}", flush=True)
    sys.exit(1)

logger = setup_logger(__name__)
print("Logger setup complete", flush=True)

# Test document
TEST_DOCUMENT = """The fund may invest in equity options and index futures. Warrants may also be used for hedging."""

async def test_derivatives():
    """Test derivatives processing with minimal document"""
    print("=" * 80)
    print("DERIVATIVES DIAGNOSTIC TEST")
    print("=" * 80)
    print(f"\nTest Document:\n{TEST_DOCUMENT}\n")
    print("=" * 80)
    
    # Initialize services
    llm_service = LLMService()
    analysis_service = AnalysisService(llm_service=llm_service)
    
    # Step 1: Get raw LLM response
    print("\n[STEP 1] Getting raw LLM response...")
    print("-" * 80)
    
    try:
        raw_llm_response = await llm_service.analyze_document(
            TEST_DOCUMENT,
            "openai",
            "gpt-4o-mini"  # Use cheaper model for testing
        )
        
        print("\n✅ Raw LLM Response (JSON):")
        print(json.dumps(raw_llm_response, indent=2, ensure_ascii=False))
        
        # Extract instrument rules
        instrument_rules = raw_llm_response.get("instrument_rules", [])
        print(f"\n📊 Instrument Rules Count: {len(instrument_rules)}")
        
        # Check derivatives-related rules
        derivatives_rules = []
        for rule in instrument_rules:
            instrument_name = rule.get("instrument", "") if isinstance(rule, dict) else getattr(rule, "instrument", "")
            instrument_lower = instrument_name.lower()
            if any(term in instrument_lower for term in ["derivative", "future", "option", "warrant"]):
                derivatives_rules.append(rule)
        
        print(f"\n🔍 Derivatives-related rules found: {len(derivatives_rules)}")
        for i, rule in enumerate(derivatives_rules, 1):
            if isinstance(rule, dict):
                print(f"  [{i}] instrument='{rule.get('instrument')}', allowed={rule.get('allowed')}, reason='{rule.get('reason', '')[:100]}...'")
            else:
                print(f"  [{i}] instrument='{getattr(rule, 'instrument', 'unknown')}', allowed={getattr(rule, 'allowed', None)}, reason='{getattr(rule, 'reason', '')[:100]}...'")
        
    except Exception as e:
        print(f"\n❌ Error getting raw LLM response: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 2: Run full analysis
    print("\n\n[STEP 2] Running full analysis service...")
    print("-" * 80)
    
    try:
        # Create empty OCRD structure
        data = analysis_service._create_empty_ocrd_json("test_fund")
        
        # Convert LLM response
        print("\n🔄 Converting LLM response to OCRD format...")
        converted_data = analysis_service._convert_llm_response_to_ocrd_format(raw_llm_response, full_text=TEST_DOCUMENT)
        
        print("\n✅ Final Post-Processed Result:")
        print("=" * 80)
        
        # Extract derivative sections
        derivative_section = converted_data.get("sections", {}).get("derivative", {})
        
        if not derivative_section:
            print("\n❌ ERROR: No 'derivative' section found in final result!")
            print(f"Available sections: {list(converted_data.get('sections', {}).keys())}")
        else:
            print("\n📋 Derivative Section Structure:")
            print(f"  Subtypes: {list(derivative_section.keys())}")
            
            # Check each subtype
            for subtype in ["future", "option", "warrant"]:
                print(f"\n{'=' * 80}")
                print(f"SUBTYPE: {subtype.upper()}")
                print(f"{'=' * 80}")
                
                if subtype not in derivative_section:
                    print(f"  ❌ Subtype '{subtype}' not found in derivative section")
                    continue
                
                subtype_data = derivative_section[subtype]
                
                # Count instruments
                instruments = {k: v for k, v in subtype_data.items() if k != "special_other_restrictions" and isinstance(v, dict)}
                print(f"  📊 Total instruments: {len(instruments)}")
                
                # Check statuses
                allowed_count = sum(1 for v in instruments.values() if v.get("allowed") is True)
                prohibited_count = sum(1 for v in instruments.values() if v.get("allowed") is False)
                undetermined_count = sum(1 for v in instruments.values() if v.get("allowed") is None)
                
                print(f"  ✅ Allowed: {allowed_count}")
                print(f"  ❌ Prohibited: {prohibited_count}")
                print(f"  ⚠️  Undetermined: {undetermined_count}")
                
                # Show sample instruments
                print(f"\n  📝 Sample instruments (first 5):")
                for i, (key, value) in enumerate(list(instruments.items())[:5], 1):
                    allowed = value.get("allowed")
                    evidence = value.get("evidence", {}).get("text", "")
                    note = value.get("note", "")
                    
                    status = "✅ Allowed" if allowed is True else ("❌ Prohibited" if allowed is False else "⚠️  Undetermined")
                    print(f"    [{i}] {key}: {status}")
                    if evidence:
                        print(f"        Evidence: {evidence[:100]}...")
                    if note:
                        print(f"        Note: {note[:100]}...")
            
            # Check for parent "Derivatives" category
            print(f"\n{'=' * 80}")
            print("PARENT: DERIVATIVES")
            print(f"{'=' * 80}")
            print("  ℹ️  Note: Parent 'Derivatives' category status is derived from children")
            print("  ℹ️  (No separate parent row exists in OCRD structure)")
            
            # Aggregate from children
            all_child_statuses = []
            for subtype in ["future", "option", "warrant"]:
                if subtype in derivative_section:
                    subtype_data = derivative_section[subtype]
                    for key, value in subtype_data.items():
                        if key != "special_other_restrictions" and isinstance(value, dict):
                            all_child_statuses.append(value.get("allowed"))
            
            if all_child_statuses:
                has_any_allowed = any(s is True for s in all_child_statuses)
                all_prohibited = all(s is False for s in all_child_statuses if s is not None)
                
                if has_any_allowed:
                    print("  ✅ Derived Status: ALLOWED (at least one child is allowed)")
                elif all_prohibited:
                    print("  ❌ Derived Status: PROHIBITED (all children are prohibited)")
                else:
                    print("  ⚠️  Derived Status: UNDETERMINED (mixed or undetermined children)")
            else:
                print("  ⚠️  Derived Status: UNDETERMINED (no child statuses found)")
        
        # Show notes
        notes = converted_data.get("notes", [])
        if notes:
            print(f"\n{'=' * 80}")
            print("NOTES:")
            print(f"{'=' * 80}")
            for note in notes[-10:]:  # Show last 10 notes
                print(f"  • {note}")
        
    except Exception as e:
        print(f"\n❌ Error in full analysis: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 3: Comparison
    print(f"\n\n{'=' * 80}")
    print("COMPARISON & DIAGNOSIS")
    print(f"{'=' * 80}")
    
    # Check if LLM returned derivatives rules
    has_derivatives_in_llm = len(derivatives_rules) > 0
    llm_allowed_derivatives = any(
        (r.get("allowed") if isinstance(r, dict) else getattr(r, "allowed", None)) is True
        for r in derivatives_rules
    )
    
    # Check final result
    final_has_allowed = False
    if derivative_section:
        for subtype in ["future", "option", "warrant"]:
            if subtype in derivative_section:
                subtype_data = derivative_section[subtype]
                for key, value in subtype_data.items():
                    if key != "special_other_restrictions" and isinstance(value, dict):
                        if value.get("allowed") is True:
                            final_has_allowed = True
                            break
                if final_has_allowed:
                    break
    
    print(f"\n📊 Summary:")
    print(f"  LLM returned derivatives rules: {has_derivatives_in_llm}")
    print(f"  LLM marked any derivative as allowed: {llm_allowed_derivatives}")
    print(f"  Final result has any derivative allowed: {final_has_allowed}")
    
    print(f"\n🔍 Diagnosis:")
    if not has_derivatives_in_llm:
        print("  ❌ PROBLEM: LLM didn't extract any derivatives rules from document")
        print("     → Issue is in LLM prompt/schema - model is biased against derivatives")
    elif not llm_allowed_derivatives:
        print("  ❌ PROBLEM: LLM extracted derivatives but marked them as not allowed")
        print("     → Issue is in LLM prompt - model defaults to 'not allowed'")
    elif not final_has_allowed:
        print("  ❌ PROBLEM: LLM marked derivatives as allowed, but final result shows not allowed")
        print("     → Issue is in Excel mapping or post-processing rules")
        print("     → Check validation logic and post-processing steps")
    else:
        print("  ✅ SUCCESS: Derivatives are correctly marked as allowed in both LLM and final result")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    try:
        asyncio.run(test_derivatives())
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
