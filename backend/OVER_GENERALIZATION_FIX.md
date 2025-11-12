# Fix for Over-Generalization of Investment Rules

## Problem Identified

The LLM was incorrectly over-generalizing investment rules. For example:
- Document states: "Unlisted equities and securities with equity character are allowed"
- LLM incorrectly inferred: ALL bonds are allowed (including `public_mortgage_bond`, `convertible_bond_regular`, `commercial_paper`, etc.)

This is a **critical error** in investment compliance because:
- Investment rules must be precise and specific
- A rule about "securities with equity character" does NOT apply to regular debt instruments like bonds
- Over-generalization can lead to incorrect compliance decisions

## Root Cause

The prompts were using broad "semantic matching" that allowed the LLM to:
1. Match general rules to specific instruments that weren't actually mentioned
2. Assume that if a category is allowed, all sub-categories are also allowed
3. Apply rules to instruments that share some characteristics but aren't the same

## Solution Implemented

### 1. Added Explicit Anti-Over-Generalization Rules

Added to all prompts:
```
**CRITICAL: DO NOT OVER-GENERALIZE RULES**
- A rule about "securities with equity character" does NOT mean ALL bonds are allowed
- A rule about "equity index options" does NOT mean ALL convertible bonds are allowed
- A rule about "unlisted equities" does NOT mean ALL debt instruments are allowed
- ONLY match if the SPECIFIC instrument name or a DIRECT synonym is mentioned in the SAME context as the rule
```

### 2. Required Direct Context Matching

Updated Excel mapping service to require:
- The instrument name must appear in the SAME sentence or paragraph as the rule
- The rule must explicitly mention the instrument type, not just a broader category
- If a general rule is found but the specific instrument is NOT mentioned in that context, mark as "not found"

### 3. Added Specific Examples

Included concrete examples:
- ✅ Correct: "convertible bonds are allowed" → match for "convertible_bond" instruments
- ❌ Incorrect: "securities with equity character are allowed" → match for ALL bonds
- ✅ Correct: "securities with equity character are allowed" → ONLY match instruments explicitly described as having equity character

## Files Updated

1. **`backend/app/services/excel_mapping_service.py`**
   - Added "DO NOT OVER-GENERALIZE RULES" section
   - Added matching requirements that require direct context
   - Added examples of correct vs incorrect matching

2. **`backend/app/services/llm_service.py`**
   - Added "DO NOT OVER-GENERALIZE RULES" to SYSTEM_PROMPT
   - Added anti-over-generalization section to user prompts
   - Added specific examples

3. **`backend/app/services/providers/openai_provider.py`**
   - Added "DO NOT OVER-GENERALIZE RULES" to system prompt
   - Added anti-over-generalization section to user prompt

## Expected Behavior After Fix

### Before (Incorrect):
- Document: "Unlisted equities and securities with equity character are allowed"
- LLM Result: ALL bonds marked as allowed (incorrect)

### After (Correct):
- Document: "Unlisted equities and securities with equity character are allowed"
- LLM Result: Only instruments explicitly described as having equity character are marked as allowed
- Regular bonds, mortgage bonds, commercial paper, etc. are NOT marked as allowed unless explicitly mentioned

## Testing Recommendations

Test with documents containing:
1. General rules like "securities with equity character are allowed"
   - Should NOT mark all bonds as allowed
   - Should ONLY mark instruments explicitly described as having equity character

2. Specific rules like "convertible bonds are allowed"
   - Should mark convertible bonds as allowed
   - Should NOT mark other bond types as allowed

3. Rules about equity instruments
   - Should NOT be applied to debt instruments
   - Should ONLY apply to the specific instrument types mentioned

## Key Principle

**A rule applies ONLY to instruments that are EXPLICITLY mentioned in the rule statement. Do NOT assume a general rule applies to all similar instruments.**

