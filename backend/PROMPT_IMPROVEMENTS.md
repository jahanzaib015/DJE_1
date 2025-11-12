# LLM Prompt Improvements for Allowed/Prohibited Rules

## Problem
The LLM was missing allowed/permitted rules, especially for instruments like "FX Forwards" and "currency futures". It was defaulting to "not allowed" when rules weren't explicitly stated.

## Solution
Enhanced all LLM prompts across the system to:

1. **Prioritize finding ALLOWED items first** - Make it clear that allowed items are just as important as prohibited ones
2. **Explicit default assumption** - Do NOT mark as "not allowed" unless explicitly prohibited
3. **Better instrument name recognition** - Recognize variations like:
   - "FX Forwards" = "forex forwards" = "foreign exchange forwards" = "FX" = "forex"
   - "currency futures" = "FX futures" = "foreign exchange futures" = "forex futures"
4. **Concrete examples** - Added specific examples showing how to extract allowed rules
5. **Step-by-step instructions** - Clear two-step process: search for allowed first, then prohibited

## Files Updated

### 1. `backend/app/services/llm_service.py`
- Enhanced `SYSTEM_PROMPT` with stronger emphasis on finding allowed items
- Updated `user_prompt` in `analyze_document` method
- Updated prompt in `_get_llm_messages` method

### 2. `backend/app/services/providers/openai_provider.py`
- Enhanced system prompt in `_analyze_with_model` method
- Updated user prompt with step-by-step instructions

### 3. `backend/app/services/excel_mapping_service.py`
- Enhanced prompt in `search_document_with_llm` method
- Added priority instructions for finding allowed items first
- Added FX/forex instrument name variations

## Key Changes

### Before:
- Generic instruction to "look for both allowed and prohibited"
- No explicit default assumption
- Limited instrument name recognition

### After:
- **STEP 1: SEARCH FOR ALLOWED ITEMS FIRST** (explicit priority)
- **STEP 2: THEN SEARCH FOR PROHIBITED ITEMS**
- Clear default: "DO NOT mark as 'not allowed' unless explicitly prohibited"
- Specific examples: "If document says 'FX Forwards are allowed' → extract with allowed=true"
- Instrument name variations explicitly listed

## Testing Recommendations

1. Test with documents containing:
   - "FX Forwards are allowed"
   - "currency futures are permitted"
   - "forex is authorized"
   - Lists of permitted instruments

2. Verify that:
   - Allowed items are extracted correctly
   - Instrument name variations are recognized
   - No false "not allowed" classifications
   - Both allowed and prohibited items are found

## Expected Behavior

When the document states:
- "FX Forwards are allowed" → Should extract: `{"instrument": "FX Forwards", "allowed": true, "reason": "Document explicitly states FX Forwards are allowed"}`
- "currency futures are permitted" → Should extract: `{"instrument": "currency futures", "allowed": true, "reason": "Document explicitly states currency futures are permitted"}`

The LLM should now prioritize finding these positive permission statements and extract them correctly.

