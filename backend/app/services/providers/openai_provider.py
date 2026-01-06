import httpx
import json
import os
import re
import sys
from typing import Dict, List
from ..interfaces.llm_provider_interface import LLMProviderInterface
from ...models.llm_response_models import LLMResponse

# Add backend directory to path to import config
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from config import OPENAI_API_KEY
from ...utils.logger import setup_logger

logger = setup_logger(__name__)


def _clean_json_string(json_str: str) -> str:
    """
    Remove invalid control characters from JSON string that cause parse errors.
    Control characters (0x00-0x1F) except \n, \r, \t are not allowed in JSON.
    """
    # Remove control characters except newline, carriage return, and tab
    # This regex matches control chars (0x00-0x1F) except \n (0x0A), \r (0x0D), \t (0x09)
    cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', json_str)
    return cleaned


class OpenAIProvider(LLMProviderInterface):
    """OpenAI ChatGPT provider with enforced JSON output and GPT-5 fallback"""

    def __init__(self):
        self.api_key = OPENAI_API_KEY
        if not self.api_key:
            logger.warning("⚠️ OPENAI_API_KEY not configured. OpenAI provider will not be available.")
            self.api_key = None

        self.base_url = "https://api.openai.com/v1"
        # Preferred model order (fastest first for speed optimization)
        # gpt-5.2 is the latest and most capable model, gpt-4o-mini is 2-3x faster than gpt-4o with similar quality
        # Removed deprecated models: gpt-4, gpt-4-turbo, gpt-3.5-turbo
        self.model_priority = ["gpt-5.2", "gpt-5.1", "gpt-5", "gpt-4o", "gpt-4o-mini"]

    async def analyze_document(self, text: str, model: str) -> Dict:
        """Analyze document using OpenAI ChatGPT with automatic fallback chain"""
        if not self.api_key:
            raise Exception("OpenAI API key not configured. Please set OPENAI_API_KEY environment variable.")

        # Try the provided model first, then fallback in priority order
        tried_models = []
        for m in [model] + [x for x in self.model_priority if x != model]:
            try:
                return await self._analyze_with_model(text, m)
            except Exception as e:
                err_msg = str(e).lower()
                tried_models.append(m)
                logger.warning(f"⚠️ Model '{m}' failed: {e}")
                if "404" in err_msg or "does not exist" in err_msg:
                    logger.info(f"⏭️ Skipping unavailable model '{m}'...")
                    continue
                if "quota" in err_msg or "limit" in err_msg or "context length" in err_msg or "maximum context" in err_msg:
                    logger.warning(f"⏭️ Skipping model '{m}' due to quota/context limit...")
                    continue
                # Only retry if next model available
                continue

        # If all models fail, return fallback
        return {
            "sector_rules": [],
            "country_rules": [],
            "instrument_rules": [],
            "conflicts": [{"category": "system_error", "detail": f"All models failed: {tried_models}"}]
        }

    async def _analyze_with_model(self, text: str, model: str) -> Dict:
        """Core analysis call to OpenAI API"""
        # Calculate safe text limit based on model context window
        # GPT-4o: 128k tokens (~512k chars), GPT-5: 128k+ tokens (assumed)
        # Reserve tokens for system prompt, user prompt template, and completion
        # Note: gpt-4 and gpt-4-turbo checks kept for backward compatibility but these models are deprecated
        if model == "gpt-4":
            # GPT-4 has 8192 token limit: reserve ~1200 for enhanced prompts, ~2000 for completion = ~5000 tokens (~10000 chars) for document
            max_text_length = 10000  # Very conservative limit to ensure we stay within 8k token context
        elif model == "gpt-4-turbo":
            # GPT-4-turbo has larger context, but be conservative
            max_text_length = 25000
        elif model == "gpt-5" or model == "gpt-5.1" or model == "gpt-5.2":
            # GPT-5/GPT-5.1/GPT-5.2 assumed to have large context window (128k+ tokens) - support very large files
            max_text_length = 1000000  # 1MB chars for very large documents (150+ pages)
        else:
            max_text_length = 500000  # 500k chars for large documents (GPT-4o, etc.)
        
        # For very large documents, section-based processing will handle chunking
        # Only truncate for deprecated models (GPT-4, GPT-4-turbo)
        if model in ("gpt-4", "gpt-4-turbo") and len(text) > max_text_length:
            logger.warning(f"Document is {len(text)} chars, truncating to {max_text_length} for {model} (deprecated model)")
            text_to_analyze = text[:max_text_length]
        else:
            # For modern models, use full text (section-based extraction will chunk it)
            text_to_analyze = text
            if len(text) > max_text_length:
                logger.info(f"Large document ({len(text)} chars) - section-based chunking will handle this")
        
        # Enhanced prompt that strongly emphasizes finding ALLOWED items
        prompt = f"""You are analyzing an investment policy document (Verkaufsprospekt, Prospectus, or similar). Your PRIMARY goal is to find ALL items that are explicitly stated as ALLOWED or PERMITTED.

🚨🚨🚨 **MANDATORY: FUTURES & OPTIONS CLASSIFICATION - READ THIS FIRST - CRITICAL ERROR PREVENTION** 🚨🚨🚨

**THE MOST COMMON AND CRITICAL ERROR IS MARKING PROHIBITED FUTURES/OPTIONS AS ALLOWED. YOU MUST FOLLOW THESE RULES EXACTLY:**

**🔴 ABSOLUTE RULE: SWAPS ARE ALWAYS NOT ALLOWED (NO EXCEPTIONS)**
- **SWAPS ARE ALWAYS PROHIBITED** - mark as allowed=false (NOT ALLOWED) regardless of what the document says
- Do NOT check the document for swaps - just mark them as allowed=false
- If you see "Swaps" mentioned anywhere, extract it as: {{"instrument": "Swaps", "allowed": false, "reason": "Swaps are always prohibited"}}
- This rule applies to ALL types of swaps: interest rate swaps, currency swaps, credit default swaps, total return swaps, etc.
- **NO EXCEPTIONS - SWAPS ARE NEVER ALLOWED**

**STEP 1: MANDATORY PROHIBITION CHECK (DO THIS FIRST FOR EVERY FUTURE/OPTION)**
Before you even consider marking ANY future or option as allowed=true, you MUST:
1. Search the ENTIRE document for explicit prohibitions on "Futures" or "Options"
2. Look for these prohibition markers:
   - "Futures: -" or "Options: -" (dash/hyphen mark)
   - "Futures: nein" or "Options: nein" (German "no")
   - "Futures" or "Options" in "Unzulässige Anlagen" section
   - "Futures" or "Options" with "X" in "nein" column of tables
   - "Futures" or "Options" with "-" in "ja" column and "X" in "nein" column
   - Any text saying "Futures are prohibited" or "Options are not allowed"
3. **IF YOU FIND ANY PROHIBITION MARKER → IMMEDIATELY mark as allowed=false (NOT ALLOWED)**
4. **DO NOT PROCEED TO CHECK FOR ALLOWANCE UNTIL YOU HAVE VERIFIED NO PROHIBITION EXISTS**

**STEP 2: DO NOT ASSUME FROM "DERIVATIVES" RULE**
- "Derivatives: X" or "Derivatives are allowed" DOES NOT mean Futures/Options are allowed
- You MUST find explicit evidence for "Futures" or "Options" specifically
- If you see "Derivatives: X" but "Futures: -" → Futures are PROHIBITED (allowed=false)
- If you see "Derivatives: X" but "Options: nein" → Options are PROHIBITED (allowed=false)
- **SPECIFIC PROHIBITIONS ALWAYS WIN - they override any general allowance**

**STEP 3: MANDATORY VALIDATION BEFORE MARKING AS ALLOWED**
Before marking any future or option as allowed=true, you MUST verify ALL of these:
- ✅ You checked for prohibitions and found NONE
- ✅ You found explicit allowance evidence (X in ja column, "erlaubt", "zulässig", in "Zulässige Anlagen")
- ✅ The document explicitly states "Futures are allowed" or "Options are allowed" (not just "derivatives")
- ✅ You checked the SPECIFIC "Futures" or "Options" row in tables (not just "Derivatives" row)

**STEP 4: EXAMPLES - MEMORIZE THESE PATTERNS**
❌ **WRONG (THIS IS THE ERROR TO AVOID):**
   Document: "Derivatives: X" and "Futures: -"
   Your extraction: {{"instrument": "Futures", "allowed": true}} ← THIS IS WRONG!
   Correct: {{"instrument": "Futures", "allowed": false}} ← Futures are PROHIBITED

✅ **CORRECT:**
   Document: "Derivatives: X" and "Futures: -"
   Your extraction: {{"instrument": "Derivatives", "allowed": true}}, {{"instrument": "Futures", "allowed": false}}

✅ **CORRECT:**
   Document: "Futures: X" in "ja" column
   Your extraction: {{"instrument": "Futures", "allowed": true}}

❌ **WRONG:**
   Document: "Derivatives: X" (no mention of Futures)
   Your extraction: {{"instrument": "Futures", "allowed": true}} ← WRONG! No explicit evidence
   Correct: Do not extract Futures at all, or extract with allowed=false if mentioned

**STEP 5: FINAL CHECKLIST BEFORE SUBMITTING**
For EVERY future and option you extract, verify:
- [ ] I checked for explicit prohibitions FIRST
- [ ] I found NO prohibition markers (no "-", no "nein", not in prohibited section)
- [ ] I found explicit allowance evidence (X in ja column, "erlaubt", etc.)
- [ ] I did NOT assume from "Derivatives" rule alone
- [ ] I checked the specific "Futures"/"Options" row, not just "Derivatives" row

**IF YOU ARE UNSURE → MARK AS allowed=false (NOT ALLOWED). It is better to be conservative than to incorrectly mark a prohibited instrument as allowed.**

🚨 **REMEMBER: A prohibited future/option marked as allowed=true is a CRITICAL ERROR. Always check prohibitions FIRST.** 🚨

**═══════════════════════════════════════════════════════════════════════════════**

**CRITICAL: HANDLING LONG DOCUMENTS (VERKAUFSPROSPEKT, PROSPECTUS, ETC.)**
This document may be very long (100+ pages). You MUST:
1. **Systematically process EVERY section** - do not skip any part of the document
2. **Search methodically**: Introduction → Investment Policy → Restrictions → Appendices → Tables → Footnotes
3. **Extract from ALL locations**: Rules can be in main text, tables, footnotes, appendices, sidebars, or any section
4. **For long documents, rules are often scattered** - you must search thoroughly through the entire document
5. **DO NOT return empty results** - if this is an investment policy document, it MUST contain rules. If you find rules, extract them. If you don't find explicit rules, check again more carefully.
6. **Long documents often have comprehensive lists** - when you see lists (especially under "Zulässige Anlagen" or "Unzulässige Anlagen"), extract EVERY single item
7. **Tables are critical in long documents** - extract every table row that contains investment rules, even if the table spans multiple pages

**CRITICAL: GERMAN DOCUMENT PATTERNS**
In German documents, X and - marks indicate allowed/prohibited status:
- An "X" (cross) mark means ALLOWED/Permitted - can appear in tables, lists, inline text, or any context (not just checkboxes)
- A "-" (hyphen/dash) mark means NOT ALLOWED/Prohibited - can appear in tables, lists, inline text, or any context
- Examples: "FX Forwards X", "Derivatives (X)", "Options: -", "Bonds -"
- "ja" = yes/allowed, "nein" = no/not allowed
- "erlaubt", "zugelassen", "berechtigt", "darf" = allowed/permitted
- "verboten", "nicht erlaubt", "ausgeschlossen", "darf nicht" = prohibited/not allowed

**CRITICAL: GERMAN SECTION HEADERS WITH LISTS**
When you see these German section headers, you MUST extract EVERY item in the list that follows:
- "Zulässige Anlagen" or "Zulässige Anlageinstrumente" = Permitted Investments → Extract EVERY item in the list as allowed=true
- "Unzulässige Anlagen" or "Unzulässige Anlageinstrumente" = Prohibited Investments → Extract EVERY item in the list as allowed=false
- These lists can be formatted as bullet points, numbered lists, comma-separated items, or table rows
- Each item in the list is a separate instrument that must be extracted individually
- Example: If you see "Zulässige Anlagen: Aktien, Bezugsrechte, Schatzanweisungen" → extract 3 separate rules:
  * {{"instrument": "Aktien", "allowed": true, "reason": "Listed in Zulässige Anlagen section"}}
  * {{"instrument": "Bezugsrechte", "allowed": true, "reason": "Listed in Zulässige Anlagen section"}}
  * {{"instrument": "Schatzanweisungen", "allowed": true, "reason": "Listed in Zulässige Anlagen section"}}

**CRITICAL: DOCUMENT VERSIONING/TRACK CHANGES (if applicable)**
Some documents use color coding to show version changes. If you detect versioning indicators:
- RED text/lines or strikethrough text = DELETED/EXCLUDED from current version - COMPLETELY IGNORE this text, do NOT extract any rules from it
- GREEN text/lines = NEW additions in current version - EXTRACT RULES FROM THIS (these are part of the current document)
- BLACK text/lines (normal text) = UNCHANGED in current version - EXTRACT RULES FROM THIS (these are part of the current document)
- If the document has versioning colors, ONLY extract rules from BLACK and GREEN text. IGNORE any RED text as it represents deleted content that is no longer valid.
- If the document does NOT have versioning colors, process all text normally using the standard extraction rules above.

**STEP 1: SEARCH FOR ALLOWED ITEMS (BE VERY THOROUGH!)**
Actively search for and extract EVERY item explicitly stated as allowed. Look for:

**A. GERMAN SECTION HEADERS (HIGHEST PRIORITY):**
- "Zulässige Anlagen", "Zulässige Anlageinstrumente", "Erlaubte Anlagen", "Zugelassene Anlagen"
- When you see ANY of these headers, extract EVERY item in the following list as allowed=true
- These lists can be bullet points, numbered lists, comma-separated, or table rows
- **VERIFICATION**: Count items - if you see 20 items, extract all 20

**B. TABLES WITH "ja/nein" COLUMNS:**
- Look for tables with "ja" (yes) and "nein" (no) columns
- If "ja" column has "X" or checkmark → that instrument is ALLOWED (allowed=true)
- Extract EVERY row from these tables

**C. EXPLICIT LANGUAGE:**
- English: "allowed", "permitted", "authorized", "approved", "may invest", "can invest"
- German: "erlaubt", "zugelassen", "berechtigt", "darf", "ja", "zulässig"
- An "X" mark in any context (tables, lists, inline text) - THIS MEANS ALLOWED!

**D. COMPREHENSIVE LISTS:**
- Long documents often have 20-50+ allowed instruments in lists
- Don't stop after finding a few - search the entire document thoroughly
- Check appendices, footnotes, and supplementary sections

**STEP 2: THEN SEARCH FOR PROHIBITED ITEMS**
Extract items explicitly stated as:
- "prohibited", "forbidden", "not allowed", "restricted", "excluded", "may not invest"
- German: "verboten", "nicht erlaubt", "ausgeschlossen", "darf nicht", "nein"
- A "-" (hyphen) mark in any context (tables, lists, inline text - German style)
- **MOST IMPORTANTLY: When you see "Unzulässige Anlagen" section, extract EVERY single item in that list**

**INSTRUMENT NAME RECOGNITION:**
Recognize these as the SAME instrument types (use the exact name from document):
- "FX Forwards" = "forex forwards" = "foreign exchange forwards" = "FX" = "forex"
- "currency futures" = "FX futures" = "foreign exchange futures" = "forex futures"
- "derivatives" includes: options, futures, forwards, swaps, warrants
- **CRITICAL FOR INDEX FUTURES/OPTIONS**: Any variant of "index future" (e.g., "equity index future", "equity index futures", "Aktienindexfutures") should be treated as "index future" for rule matching. Any variant of "index option" (e.g., "equity index option", "equity index options", "Aktienindexoptionen") should be treated as "index option" for rule matching. Extract the exact name from the document, but the system will map it to the base category.
- German terms: "Aktien" = stocks/shares, "Anleihen" = bonds, "Schatzanweisungen" = treasury bills, "Bezugsrechte" = subscription rights, etc.

**WHAT TO EXTRACT:**
- Sectors: Energy, Healthcare, Defense, Tobacco, Weapons, Technology, etc.
- Countries: USA, China, Russia, Europe, UK, etc.
- Instruments: Use EXACT names from document (e.g., "FX Forwards", "currency futures", "covered bonds", "common stock", "Aktien", "Bezugsrechte", "Schatzanweisungen", etc.)
- **Extract each instrument individually - do not group them together**
- **🔴 SWAPS**: If "Swaps" is mentioned anywhere in the document, ALWAYS extract as: {{"instrument": "Swaps", "allowed": false, "reason": "Swaps are always prohibited"}} - No checking needed, always not allowed

**CRITICAL RULES:**
1. If document says "FX Forwards are allowed" → extract: {{"instrument": "FX Forwards", "allowed": true, "reason": "Document explicitly states FX Forwards are allowed"}}
2. If document says "currency futures are permitted" → extract: {{"instrument": "currency futures", "allowed": true, "reason": "Document explicitly states currency futures are permitted"}}
3. If document has a section "Zulässige Anlagen" with a list of 20 items → extract 20 separate instrument rules, one for each item
4. If document has a section "Unzulässige Anlagen" with a list of 15 items → extract 15 separate instrument rules, one for each item
5. DO NOT mark something as "not allowed" unless explicitly prohibited
6. Search ENTIRE document - rules can be in any section, table, footnote, or appendix
7. **DO NOT SKIP ITEMS IN LISTS - extract every single instrument mentioned**
8. **CRITICAL FOR TABLES: Include every table row, even nested/sub-items, as a separate entry. Extract each row individually - do not skip any rows in tables.**

**DO NOT OVER-GENERALIZE:**
- If document says "securities with equity character are allowed" → this ONLY applies to instruments explicitly described as having equity character, NOT to all bonds
- If document says "equity index options are allowed" → this ONLY applies to equity index options, NOT to all convertible bonds or structured products
- If document says "unlisted equities are allowed" → this ONLY applies to unlisted equities, NOT to debt instruments like bonds
- ONLY extract rules when the SPECIFIC instrument type is mentioned in the rule statement
- DO NOT assume a general rule applies to all similar instruments

**CRITICAL: PARENT CATEGORIES VS SUBTYPES - CHECK SUBTYPES SEPARATELY**
⚠️ **MOST IMPORTANT RULE**: If a broader category (e.g., "Bonds", "Renten", "Derivatives", "Futures", "Options") is allowed, that does NOT mean all subtypes are allowed!
- Example: If document says "Bonds: Ja/Yes" (allowed), you MUST still check each bond subtype separately
- Example: Document may show "4.2. Renten / Bonds: Ja/Yes" BUT then show "4.2.2.2. Pfandbriefe / Covered bonds: Nein/No"
- Example: Document may show "4.6. Derivate / Derivatives: Ja/Yes" AND "4.6.1. Futures / Futures: Ja/Yes" AND "4.6.2. Börsengehandelte Optionen / Exchange traded options: Ja/Yes" BUT "4.6.3. Optionsscheine / Warrants: Nein/No"
- **ALWAYS extract rules for subtypes individually** - do NOT assume they inherit from parent category
- If you see a table with parent category "Bonds: Ja/Yes" followed by many subtypes with "Nein/No", extract ALL of them:
  * Extract: "Bonds" = allowed=true
  * Extract: "Covered bonds" = allowed=false
  * Extract: "Corporate bonds" = allowed=false
  * Extract: "Asset backed securities" = allowed=false
  * etc.
- If you see a derivatives table with "Derivatives: Ja/Yes", "Futures: Ja/Yes", "Options: Ja/Yes", "Warrants: Nein/No", extract ALL of them:
  * Extract: "Derivatives" = allowed=true
  * Extract: "Futures" = allowed=true
  * Extract: "Options" = allowed=true
  * Extract: "Warrants" = allowed=false
- **Specific subtype rules ALWAYS take precedence over parent category rules**
- When you see a parent category allowed, you MUST check if there are subtype restrictions in the same table/section
- Extract EVERY row from tables, including nested sub-items - each subtype needs its own rule entry

**CRITICAL: FUTURES AND OPTIONS CLASSIFICATION (HIGHEST PRIORITY - PREVENTS MISCLASSIFICATION)**
⚠️ **MOST COMMON ERROR**: Marking futures/options as allowed when they are actually prohibited. Follow these rules STRICTLY:

**RULE 1: CHECK FOR EXPLICIT PROHIBITIONS FIRST (BEFORE CHECKING ALLOWED STATUS)**
- **BEFORE** marking any future or option as allowed, you MUST check if it's explicitly prohibited
- If you see "Futures: -" or "Options: -" or "Futures: nein" or "Options: nein" → mark as allowed=false (NOT ALLOWED)
- If you see "Futures" or "Options" in "Unzulässige Anlagen" section → mark as allowed=false (NOT ALLOWED)
- If you see "Futures" or "Options" with "X" in "nein" column → mark as allowed=false (NOT ALLOWED)
- **SPECIFIC PROHIBITIONS ALWAYS OVERRIDE GENERAL ALLOWANCES**

**RULE 2: DO NOT ASSUME FUTURES/OPTIONS ARE ALLOWED JUST BECAUSE "DERIVATIVES" IS ALLOWED**
- If document says "derivatives are allowed" or shows "Derivatives (X)" → this does NOT automatically mean all futures and options are allowed
- You MUST check for explicit mentions of "futures" or "options" separately
- Only mark futures/options as allowed if:
  * You see "Futures: X" or "Options: X" or "Futures: ja" or "Options: ja"
  * You see "Futures" or "Options" in "Zulässige Anlagen" section
  * You see "Futures" or "Options" with "X" in "ja" column
  * The document explicitly states "futures are allowed" or "options are allowed"

**RULE 3: CHECK BOTH GENERAL AND SPECIFIC RULES**
- Look for BOTH general "derivatives" rules AND specific "futures"/"options" rules
- If "derivatives" is allowed BUT "futures" is prohibited → mark futures as allowed=false
- If "derivatives" is allowed BUT "options" is prohibited → mark options as allowed=false
- Specific instrument rules (futures, options) take precedence over general category rules (derivatives)

**RULE 4: TABLE INTERPRETATION FOR FUTURES/OPTIONS**
- In tables, check the row for "Futures" or "Options" specifically
- If "Futures" row has "-" in "ja" column and "X" in "nein" column → allowed=false (NOT ALLOWED)
- If "Futures" row has "X" in "ja" column → allowed=true (ALLOWED)
- If "Options" row has "-" in "ja" column and "X" in "nein" column → allowed=false (NOT ALLOWED)
- If "Options" row has "X" in "ja" column → allowed=true (ALLOWED)
- **DO NOT** look at "Derivatives" row and assume it applies to Futures/Options - check the specific row

**RULE 5: EXAMPLES OF CORRECT CLASSIFICATION**
- ✅ CORRECT: Document shows "Derivatives: X" and "Futures: -" → Extract: {{"instrument": "Derivatives", "allowed": true}}, {{"instrument": "Futures", "allowed": false}}
- ✅ CORRECT: Document shows "Derivatives: X" and "Options: nein" → Extract: {{"instrument": "Derivatives", "allowed": true}}, {{"instrument": "Options", "allowed": false}}
- ❌ WRONG: Document shows "Derivatives: X" and "Futures: -" → Marking Futures as allowed=true (THIS IS THE ERROR TO AVOID!)
- ✅ CORRECT: Document shows "Futures: X" in "ja" column → Extract: {{"instrument": "Futures", "allowed": true}}
- ✅ CORRECT: Document shows "Options: -" in "ja" column and "X" in "nein" column → Extract: {{"instrument": "Options", "allowed": false}}

**RULE 6: WHEN IN DOUBT, CHECK FOR PROHIBITION FIRST**
- If you're unsure whether a future or option is allowed, check for explicit prohibition markers first:
  * Look for "-" mark next to "Futures" or "Options"
  * Look for "nein" or "verboten" or "nicht erlaubt" next to "Futures" or "Options"
  * Look for "Futures" or "Options" in prohibited sections
- If you find ANY prohibition marker → mark as allowed=false
- Only mark as allowed=true if you find explicit ALLOWANCE markers (X in ja column, "erlaubt", "zulässig", etc.)

**REMEMBER**: A future or option that is explicitly prohibited (with "-", "nein", or in prohibited section) is NEVER allowed, regardless of what the general "derivatives" rule says.

**Return JSON only:**
{{
  "sector_rules": [{{"sector": "string", "allowed": true/false, "reason": "string"}}],
  "country_rules": [{{"country": "string", "allowed": true/false, "reason": "string"}}],
  "instrument_rules": [{{"instrument": "string", "allowed": true/false, "reason": "string"}}],
  "conflicts": [{{"category": "string", "detail": "string"}}]
}}

**═══════════════════════════════════════════════════════════════════════════════**
**LEGEND / QUICK REFERENCE - READ THIS BEFORE ANALYZING THE DOCUMENT BELOW**
**═══════════════════════════════════════════════════════════════════════════════**

**COLOR CODING (if document has versioning/track changes):**
- 🔴 RED text/strikethrough = DELETED - IGNORE completely, do NOT extract
- 🟢 GREEN text = NEW additions - EXTRACT (current version)
- ⚫ BLACK text = UNCHANGED - EXTRACT (current version)

**SYMBOL INTERPRETATION:**
- "X" (cross mark) in "ja" column OR any context = ALLOWED (allowed=true) ⭐ MOST IMPORTANT
- "X" (cross mark) in "nein" column = NOT ALLOWED (allowed=false)
- "✓" (checkmark) in "ja" column = ALLOWED (allowed=true)
- "-" (hyphen/dash) in any column = NOT ALLOWED (allowed=false)
- Empty checkbox/cell = typically NOT ALLOWED

**TABLE COLUMN INTERPRETATION:**
- "ja" column with "X" or "✓" = ALLOWED (allowed=true) ⭐ CRITICAL RULE
- "nein" column with "X" = NOT ALLOWED (allowed=false)
- "ja" = yes/allowed | "nein" = no/not allowed

**GERMAN KEYWORDS:**
- ALLOWED: "ja", "erlaubt", "zugelassen", "berechtigt", "darf", "zulässig"
- PROHIBITED: "nein", "verboten", "nicht erlaubt", "ausgeschlossen", "darf nicht", "unzulässig"

**SECTION HEADERS:**
- "Zulässige Anlagen" / "Zulässige Anlageinstrumente" = ALL items are ALLOWED (allowed=true)
- "Unzulässige Anlagen" / "Unzulässige Anlageinstrumente" = ALL items are PROHIBITED (allowed=false)
- Extract EVERY item from these sections - count and verify completeness

**ENGLISH KEYWORDS:**
- ALLOWED: "allowed", "permitted", "authorized", "approved", "may invest", "can invest", "eligible"
- PROHIBITED: "prohibited", "forbidden", "not allowed", "restricted", "excluded", "may not invest"

**⚠️ CRITICAL: FUTURES & OPTIONS - CHECK PROHIBITIONS FIRST!**
- If "Futures: -" or "Options: -" or "Futures: nein" → NOT ALLOWED (allowed=false)
- If "Derivatives: X" but "Futures: -" → Futures are NOT ALLOWED (specific rule overrides general)
- Only mark Futures/Options as allowed if explicitly shown as allowed (X in ja column, "erlaubt", etc.)
- DO NOT assume Futures/Options are allowed just because "Derivatives" is allowed

**🔴 ABSOLUTE RULE: SWAPS ARE ALWAYS NOT ALLOWED**
- **SWAPS = ALWAYS allowed=false** - No exceptions, no checking needed
- Mark as: {{"instrument": "Swaps", "allowed": false, "reason": "Swaps are always prohibited"}}
- Applies to ALL swap types: interest rate swaps, currency swaps, credit default swaps, etc.

**REMEMBER:** Extract EVERY row from tables, count items in lists, search the ENTIRE document systematically.

**═══════════════════════════════════════════════════════════════════════════════**

**Document text to analyze (search through ALL of it systematically):**
{text_to_analyze}"""

        # Use connection pooling for faster requests (reuse connections)
        # Increased timeout for large documents, but add safety limits
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(180.0, connect=15.0, read=180.0),  # 3 min timeout for large docs
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        ) as client:
            payload = {
                "model": model,
                "store": False,  # Prevent OpenAI from storing data for GDPR compliance
                "messages": [
                    {
                        "role": "system",
                        "content": """You are an expert compliance analyst with 100% accuracy requirements specializing in investment rules extraction.

**ACCURACY REQUIREMENTS:**
- Extract ONLY rules that are EXPLICITLY stated in the document
- Use EXACT quotes from the document as evidence (copy text verbatim)
- Do NOT infer, assume, or guess - only extract what is clearly written
- Verify completeness: count items in lists and ensure you extracted all of them
- Cross-reference different sections to catch contradictions
- If a rule is ambiguous, mark it as conditional or include in conflicts

**CRITICAL INSTRUCTIONS - READ CAREFULLY:**

1. DEFAULT ASSUMPTION: All instruments are NOT ALLOWED (prohibited) unless explicitly stated as allowed/permitted. Extract all instruments mentioned in the document, defaulting to allowed=false.

2. SEARCH FOR EXPLICITLY ALLOWED ITEMS: When you find explicit evidence that an instrument is ALLOWED, mark it as allowed=true:
   - "allowed", "permitted", "authorized", "approved", "may invest", "can invest", "eligible"
   - German: "erlaubt", "zugelassen", "berechtigt", "darf", "ja", "zulässig"
   - An "X" mark in tables/lists (German style) - THIS MEANS ALLOWED!
   - Lists of permitted instruments (e.g., "Zulässige Anlagen") - extract EVERY item from these lists as allowed=true
   - **CRITICAL**: When you see "Zulässige Anlagen" section, extract EVERY single item in that list as allowed=true
   - **CRITICAL**: In tables with "ja" (yes) columns, if there's an "X" in the "ja" column, that instrument is ALLOWED

3. GERMAN DOCUMENT PATTERNS - TABLE STRUCTURE (CRITICAL - HIGHEST PRIORITY):
   **MOST IMPORTANT**: Many German investment documents use tables with "ja" (yes) and "nein" (no) columns. This is THE PRIMARY format.
   
   **TABLE FORMAT RECOGNITION:**
   - Look for tables with columns: "ja", "nein", "Detailrestriktionen"
   - Table may appear as: "Instrument | nein | ja | Detailrestriktionen"
   - Or in text: "Aktien | nein: - | ja: X | Detailrestriktionen: ..."
   - Or as list: "Aktien: nein: -, ja: X"
   - **CRITICAL**: Even if table structure is broken, look for "Instrument name" + "ja: X" patterns
   
   **INTERPRETATION (APPLY TO EACH ROW):**
   - **CRITICAL RULE**: "X" in "ja" column = ALLOWED (allowed=true) - THIS IS THE MOST IMPORTANT RULE
   - "X" in "nein" column = NOT ALLOWED (allowed=false)
   - "✓" in "ja" column = ALLOWED (allowed=true)
   - "-" in either column = typically NOT ALLOWED
   - **MOST IMPORTANT**: Extract EVERY row from these tables - count rows and extract all
   
   **OTHER PATTERNS:**
   - "ja" = yes/allowed, "nein" = no/not allowed
   - German keywords: "erlaubt", "zugelassen", "berechtigt", "darf" = allowed/permitted
   - German keywords: "verboten", "nicht erlaubt", "ausgeschlossen", "darf nicht" = prohibited/not allowed

3b. GERMAN SECTION HEADERS WITH LISTS (CRITICAL):
   - When you see "Zulässige Anlagen" or "Zulässige Anlageinstrumente" section → Extract EVERY item in the list as allowed=true
   - When you see "Unzulässige Anlagen" or "Unzulässige Anlageinstrumente" section → Extract EVERY item in the list as allowed=false
   - These lists can be formatted as bullet points, numbered lists, comma-separated items, or table rows
   - Each item in the list is a separate instrument that must be extracted individually
   - DO NOT skip any items - extract every single instrument mentioned in these sections
   - **VERIFICATION**: Count the items and ensure you extract that exact number
   - Example: If you see "Zulässige Anlagen: Aktien, Bezugsrechte, Schatzanweisungen" → extract 3 separate rules, one for each instrument

3a. DOCUMENT VERSIONING/TRACK CHANGES (if applicable):
   - Some documents use color coding to show version changes
   - RED text/lines or strikethrough text = DELETED/EXCLUDED from current version - COMPLETELY IGNORE this text, do NOT extract any rules from it
   - GREEN text/lines = NEW additions in current version - EXTRACT RULES FROM THIS (these are part of the current document)
   - BLACK text/lines (normal text) = UNCHANGED in current version - EXTRACT RULES FROM THIS (these are part of the current document)
   - If the document has versioning colors, ONLY extract rules from BLACK and GREEN text. IGNORE any RED text as it represents deleted content that is no longer valid.
   - If the document does NOT have versioning colors, process all text normally using the standard extraction rules above.

4. RECOGNIZE ALLOWED LANGUAGE (mark as allowed=true):
   - "permitted", "allowed", "authorized", "approved", "may invest", "can invest", "eligible"
   - German: "erlaubt", "zugelassen", "berechtigt", "darf", "ja", "zulässig"
   - An "X" mark in a checkbox column (German style)
   - "investments are permitted in...", "the fund may invest in...", "investments in X are allowed"
   - "FX Forwards are allowed", "currency futures are permitted", "forex is authorized"
   - Lists of permitted instruments, sectors, or countries
   - Positive statements like "investments in [X] are permitted"

5. RECOGNIZE PROHIBITED LANGUAGE (mark as allowed=false):
   - "prohibited", "forbidden", "not allowed", "restricted", "excluded", "may not invest", "not eligible"
   - German: "verboten", "nicht erlaubt", "ausgeschlossen", "darf nicht", "nein", "unzulässig"
   - A "-" (hyphen) or empty checkbox (German style)
   - "investments in X are not allowed", "prohibited from investing in..."

6. INSTRUMENT NAME VARIATIONS: Recognize that these refer to the SAME instrument type (but use EXACT name from document):
   - "FX Forwards" = "forex forwards" = "foreign exchange forwards" = "FX" = "forex" = "Foreign Exchange Forwards"
   - "currency futures" = "FX futures" = "foreign exchange futures" = "forex futures" = "Currency Futures"
   - "derivatives" includes: options, futures, forwards, swaps, warrants, structured products
   - Extract the specific instrument name as stated in the document (use exact name, do not translate)

7. EXTRACTION RULES:
   - Extract rules that are CLEARLY stated in the document (don't invent rules)
   - Look for buried rules in tables, footnotes, appendices - search the ENTIRE document systematically
   - Extract rules even if stated indirectly (e.g., "prohibited from investing in tobacco" = tobacco sector not allowed)
   - Do NOT mix different rule categories (keep sectors, countries, instruments separate)
   - If text is unclear or contradictory, record it in conflicts section
   - For tables: extract every row, including nested/sub-items, as separate entries

8. HANDLE CONDITIONAL RULES:
   - If a rule says "subject to", "provided that", "up to X%", "with restrictions" → extract with allowed=true but include condition in reason
   - Example: "FX Forwards allowed up to 10% of portfolio" → allowed=true, reason="FX Forwards allowed up to 10% of portfolio"

9. CRITICAL: DO NOT OVER-GENERALIZE RULES
   - A rule about "securities with equity character are allowed" does NOT mean ALL bonds are allowed
   - A rule about "equity index options are allowed" does NOT mean ALL convertible bonds are allowed
   - A rule about "unlisted equities are allowed" does NOT mean ALL debt instruments are allowed
   - ONLY extract rules for instruments that are EXPLICITLY mentioned in the rule statement
   - Example: If document says "convertible bonds are allowed" → extract rule for "convertible bonds" specifically
   - Example: If document says "securities with equity character are allowed" → ONLY extract for instruments explicitly described as having equity character, NOT for regular bonds
   - DO NOT assume that a general rule applies to all similar instruments

10. EVIDENCE REQUIREMENTS:
    - The "reason" field must contain the EXACT quote from the document (verbatim copy)
    - Include enough context to make the rule clear
    - If rule spans multiple sentences, include all relevant parts
    - Do not paraphrase or summarize - use exact quotes

11. COMPLETENESS VERIFICATION (MANDATORY):
    - Did you check ALL sections? (main text, tables, footnotes, appendices, introduction, investment policy, restrictions)
    - Did you extract ALL items from lists under "Zulässige Anlagen" and "Unzulässige Anlagen"?
    - Did you extract ALL rows from tables (including nested items, multi-page tables)?
    - Did you check for both allowed AND prohibited statements throughout the ENTIRE document?
    - Did you use exact quotes as evidence?
    - **CRITICAL**: Did you search systematically through the entire document, or did you only check the beginning?
    - **CRITICAL**: If this is a long document (Verkaufsprospekt/Prospectus), did you check sections that might be later in the document?
    - **CRITICAL**: Are you returning empty results? If yes, double-check - investment policy documents almost always contain rules. Search more carefully.

**IF YOU ARE RETURNING EMPTY RESULTS:**
- STOP and re-examine the document
- Look for sections titled: "Investment Policy", "Investment Restrictions", "Zulässige Anlagen", "Unzulässige Anlagen", "Permitted Investments", "Prohibited Investments", "Investment Guidelines", "Anlagegrundsätze"
- Check tables - even if they seem unrelated, they may contain investment rules
- Look for lists of instruments, sectors, or countries
- Search for keywords: "erlaubt", "zugelassen", "verboten", "nicht erlaubt", "allowed", "permitted", "prohibited", "forbidden"
- If you still find nothing, include a conflict explaining why no rules were found

Your task: Systematically search through the ENTIRE document section-by-section and extract ALL rules with maximum accuracy - prioritize finding what IS ALLOWED, then what is NOT ALLOWED. Extract every explicitly stated permission or prohibition. For long documents, be especially thorough - rules are often scattered across many sections. Verify completeness before finishing. DO NOT return empty results unless you are absolutely certain the document contains no investment rules.

Return ONLY valid JSON matching the required schema."""
                    },
                    {"role": "user", "content": prompt},
                ],
                "top_p": 1,
            }
            
            # Set temperature based on model requirements
            # gpt-5/gpt-5.1/gpt-5.2 only supports default temperature (1), not 0
            if model == "gpt-5" or model == "gpt-5.1" or model == "gpt-5.2":
                # gpt-5/gpt-5.1/gpt-5.2 requires default temperature (1) - don't set it or set to 1
                payload["temperature"] = 1
            else:
                # Other models can use temperature 0 for deterministic responses
                payload["temperature"] = 0
            
            # Use correct parameter name based on model
            # Newer models (gpt-5, gpt-5.1, gpt-5.2, gpt-4.1, o1, etc.) use max_completion_tokens
            # Older models (gpt-4o, gpt-4o-mini, etc.) use max_tokens
            if model in ["gpt-5", "gpt-5.1", "gpt-5.2"]:
                # GPT-5/5.1/5.2 have large context windows - use higher limit to avoid truncation
                payload["max_completion_tokens"] = 8000
            elif model in ["o1", "o1-mini", "o1-preview", "o1-2024-09-12", "gpt-4.1"]:
                payload["max_completion_tokens"] = 4000
            else:
                # Standard models (gpt-4o, etc.) use max_tokens
                # Increased to 4000 to avoid truncation (costs more but ensures completeness)
                # Note: gpt-4 check kept for backward compatibility but this model is deprecated
                # GPT-4 has 8k context window, so use 3500 to leave room for input
                if model == "gpt-4":
                    payload["max_tokens"] = 3500  # 8192 total - ~4500 input (enhanced prompts) - ~200 buffer for safety
                else:
                    # Modern models (gpt-4o, etc.) have larger context windows
                    payload["max_tokens"] = 4000  # Full limit for comprehensive rule extraction

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                raise Exception(
                    f"OpenAI API error ({model}): {response.status_code} - "
                    f"{error_data.get('error', {}).get('message', 'Unknown error')}"
                )

            data = response.json()
            
            # Check if response has choices
            if "choices" not in data or len(data["choices"]) == 0:
                logger.error(f"❌ Model '{model}' returned no choices in response")
                logger.error(f"❌ Full API response: {data}")
                raise Exception(f"Model '{model}' returned no choices")
            
            # Check if message content exists
            if "message" not in data["choices"][0] or "content" not in data["choices"][0]["message"]:
                logger.error(f"❌ Model '{model}' returned no message content")
                logger.error(f"❌ Full API response: {data}")
                raise Exception(f"Model '{model}' returned no message content")
            
            llm_response = data["choices"][0]["message"]["content"].strip()
            
            # Check if response is empty
            if not llm_response or len(llm_response) == 0:
                logger.error(f"❌ Model '{model}' returned empty response (0 characters)")
                logger.error(f"❌ Full API response structure: {list(data.keys())}")
                logger.error(f"❌ Choices data: {data.get('choices', [])}")
                raise Exception(f"Model '{model}' returned empty response - this may indicate an API issue, model issue, or the prompt was too long")
            
            logger.debug(f"[{model}] Raw LLM response (first 500 chars): {llm_response[:500]}")
            logger.debug(f"[{model}] Raw LLM response length: {len(llm_response)} chars")

            # Clean response - remove markdown code blocks if present
            cleaned_response = llm_response.strip().strip("```json").strip("```").strip()
            
            # Extract JSON more robustly - find first { and last } to handle extra text
            json_start = cleaned_response.find('{')
            json_end = cleaned_response.rfind('}') + 1
            
            if json_start == -1 or json_end <= json_start:
                logger.warning(f"⚠️ Model '{model}' returned invalid JSON — no JSON object found.")
                logger.warning(f"⚠️ Full response (first 1000 chars): {cleaned_response[:1000]}")
                logger.warning(f"⚠️ Full response length: {len(cleaned_response)} chars")
                logger.warning(f"⚠️ Response contains '{{': {cleaned_response.find('{') != -1}")
                logger.warning(f"⚠️ Response contains '}}': {cleaned_response.find('}') != -1}")
                # Try to find JSON array instead
                array_start = cleaned_response.find('[')
                array_end = cleaned_response.rfind(']') + 1
                if array_start != -1 and array_end > array_start:
                    logger.info(f"⚠️ Found JSON array instead of object, trying to parse...")
                    try:
                        array_str = cleaned_response[array_start:array_end]
                        # Clean invalid control characters before parsing
                        array_str = _clean_json_string(array_str)
                        parsed_array = json.loads(array_str)
                        # Convert array to object format
                        logger.info(f"⚠️ Successfully parsed JSON array, converting to object format")
                        return {
                            "sector_rules": [],
                            "country_rules": [],
                            "instrument_rules": parsed_array if isinstance(parsed_array, list) else [],
                            "conflicts": []
                        }
                    except json.JSONDecodeError:
                        pass
                return self._fallback_response(f"Invalid model output: {cleaned_response[:200]}")
            
            # Extract just the JSON portion
            json_str = cleaned_response[json_start:json_end]
            logger.debug(f"[{model}] Extracted JSON (length: {len(json_str)} chars)")

            # Clean invalid control characters before parsing
            json_str = _clean_json_string(json_str)

            try:
                parsed = json.loads(json_str)
                logger.debug(f"✅ [{model}] Successfully parsed JSON response")
                
                # Use Pydantic for validation and normalization
                try:
                    validated_response = LLMResponse.from_dict(parsed)
                    logger.debug(f"✅ [{model}] Pydantic validation passed")
                    return validated_response.to_dict()
                except Exception as validation_error:
                    logger.warning(f"⚠️ [{model}] Pydantic validation failed: {validation_error}")
                    # Fallback to manual normalization for backward compatibility
                    return self._validate_and_normalize_response(parsed)
                    
            except json.JSONDecodeError as e:
                logger.error(f"❌ Model '{model}' JSON parse failed: {e}")
                logger.debug(f"Failed to parse: {llm_response[:500]}")
                return self._fallback_response(f"Parsing error from {model}: {str(e)}")

    def _fallback_response(self, reason: str) -> Dict:
        """Return safe fallback JSON"""
        return {
            "sector_rules": [],
            "country_rules": [],
            "instrument_rules": [],
            "conflicts": [{"category": "parsing_error", "detail": reason}]
        }

    def _validate_and_normalize_response(self, parsed_json: Dict) -> Dict:
        """Ensure consistent structure for compliance analysis"""
        expected_keys = ["sector_rules", "country_rules", "instrument_rules", "conflicts"]
        normalized = {}
        
        for key in expected_keys:
            value = parsed_json.get(key, [])
            if isinstance(value, list):
                normalized[key] = value
            else:
                normalized[key] = []
        
        return normalized

    def get_available_models(self) -> List[str]:
        """List supported OpenAI models"""
        return self.model_priority

    async def generate(self, prompt: str) -> str:
        """Legacy compatibility"""
        return "generate() method placeholder — not used."
