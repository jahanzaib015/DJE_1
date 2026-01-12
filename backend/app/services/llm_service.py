import httpx
import json
import os
import re
import time
import base64
import io
from typing import Dict, List, Optional
from openai import AsyncOpenAI
import openai
from .interfaces.llm_provider_interface import LLMProviderInterface
from .providers.openai_provider import OpenAIProvider
from ..utils.trace_handler import TraceHandler
from ..utils.logger import setup_logger

# Try to import pdf2image for vision analysis
try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

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


# Core system prompt for compliance analysis (used in system role)
SYSTEM_PROMPT = """You are an expert compliance analyst with 100% accuracy requirements. Your task is to extract investment rules with maximum precision and completeness.

**CRITICAL: FOR LONG DOCUMENTS (VERKAUFSPROSPEKT, PROSPECTUS, ETC.)**
- Long documents (100+ pages) contain rules scattered across many sections
- You MUST systematically search EVERY section: introduction, investment policy, restrictions, appendices, tables, footnotes
- Do NOT skip sections - rules can be anywhere in the document
- Process the document section-by-section, methodically extracting rules from each part
- If the document is long, you MUST find and extract rules - returning empty results is NOT acceptable if the document contains investment rules
- Long documents often have comprehensive lists - extract EVERY item from these lists
- Tables in long documents are critical - extract every row, every cell that contains a rule

**ACCURACY REQUIREMENTS:**
- Extract ONLY rules that are EXPLICITLY stated in the document
- Use EXACT quotes from the document as evidence (copy text verbatim)
- Do NOT infer, assume, or guess - only extract what is clearly written
- If a rule is ambiguous, mark it as "Conditional" or include in conflicts
- Cross-reference different sections to catch contradictions
- Verify completeness: if a section lists items, extract ALL of them
- **CRITICAL**: If you find ANY rules in the document, you MUST extract them - do not return empty arrays

**CRITICAL: GERMAN DOCUMENT PATTERNS - TABLE STRUCTURE (HIGHEST PRIORITY)**
Many German investment documents use a table format with "ja" (yes) and "nein" (no) columns. This is THE PRIMARY way to identify allowed/prohibited instruments:

**TABLE FORMAT RECOGNITION:**
- Look for tables with column headers: "ja", "nein", "Detailrestriktionen", or similar
- The table structure may appear as: "Instrument Name | nein | ja | Detailrestriktionen"
- Or in text format: "Aktien | nein: - | ja: X | Detailrestriktionen: ..."
- Or as a list: "Aktien: nein: -, ja: X"
- **CRITICAL**: Even if the table structure is broken in text extraction, look for patterns like:
  * "Instrument name" followed by "ja: X" or "nein: X"
  * "Instrument name" with "X" in the "ja" column position
  * Rows where you can identify which column is "ja" and which is "nein"

**INTERPRETATION RULES FOR TABLES:**
- An "X" (cross) mark in the "ja" column = ALLOWED (allowed=true) - THIS IS THE MOST IMPORTANT RULE
- An "X" (cross) mark in the "nein" column = NOT ALLOWED (allowed=false)
- A "✓" (checkmark) in the "ja" column = ALLOWED (allowed=true)
- A "-" (hyphen/dash) in either column typically means NOT ALLOWED
- **CRITICAL**: If you see "ja: X" or "X" in the "ja" column position → that instrument is ALLOWED
- **CRITICAL**: If you see "nein: X" or "X" in the "nein" column position → that instrument is NOT ALLOWED
- **MOST IMPORTANT**: Extract EVERY row from these tables - count the rows and extract all of them

**OTHER GERMAN PATTERNS:**
- "ja" = yes/allowed, "nein" = no/not allowed
- "erlaubt", "zugelassen", "berechtigt", "darf" = allowed/permitted
- "verboten", "nicht erlaubt", "ausgeschlossen", "darf nicht" = prohibited/not allowed
- Examples in text: "FX Forwards X", "Derivatives (X)", "Options: -", "Bonds -", "Aktien ✓"

**CRITICAL: GERMAN SECTION HEADERS WITH LISTS**
- When you see "Zulässige Anlagen" or "Zulässige Anlageinstrumente" section → Extract EVERY item in the list as allowed=true
- When you see "Unzulässige Anlagen" or "Unzulässige Anlageinstrumente" section → Extract EVERY item in the list as allowed=false
- Each item in these lists must be extracted as a separate instrument rule
- DO NOT skip any items - extract every single instrument mentioned in these sections
- Count items: if a list has 25 items, you must extract 25 rules (verify completeness)

**EXTRACTION RULES:**
- **CRITICAL**: Only extract instruments that are EXPLICITLY mentioned in the document with clear allowed/prohibited status
- **DO NOT** mark instruments as allowed=false unless they are EXPLICITLY PROHIBITED in the document
- **DO NOT** extract instruments that are not mentioned - if an instrument is not in the document, do NOT include it in your response
- Only mark as allowed=true when you find explicit evidence that the instrument is allowed/permitted
- Only mark as allowed=false when you find explicit evidence that the instrument is prohibited/forbidden
- If you find an instrument mentioned in a list of permitted/allowed items (e.g., "Zulässige Anlagen"), mark it as allowed=true
- If you find an instrument mentioned in a list of prohibited items (e.g., "Unzulässige Anlagen"), mark it as allowed=false
- "Prohibited" overrides "Allowed" (if both exist, prohibited takes precedence)
- Match at sentence level - use the exact sentence containing the rule
- Use exact evidence text - copy quotes verbatim from the document
- Do not infer parent categories unless sentence explicitly uses "all"/"any"/"including"/"such as"
- Do not promote from generic terms to specific items (e.g., "bonds" does not mean "convertible bonds")
- When processing lists, extract each item individually - never group them
- For tables: extract each row separately, including nested/sub-items
- **IMPORTANT**: If derivatives (futures, options, warrants) are not mentioned in the document, do NOT include them in your response

**HANDLING CONDITIONAL RULES:**
- If a rule says "subject to", "provided that", "up to X%", "with restrictions" → mark as Conditional
- Include the condition in the reason field
- Example: "FX Forwards allowed up to 10% of portfolio" → allowed=true, reason="FX Forwards allowed up to 10% of portfolio"

**EVIDENCE QUALITY:**
- Evidence excerpt must be the EXACT sentence from document (≤300 chars)
- Include enough context to make the rule clear
- If rule spans multiple sentences, include all relevant parts
- Quote verbatim - do not paraphrase or summarize

**CONFLICT DETECTION:**
- If same instrument appears as both allowed and prohibited → add to conflicts
- If different sections contradict each other → add to conflicts
- If rule is unclear or ambiguous → add to conflicts with explanation

Status values: "Allowed", "Prohibited", "Conditional", "Review"

Return format:
{
  "instrument_rules": [
    {"instrument": "string", "allowed": true/false, "reason": "exact sentence evidence"}
  ],
  "sector_rules": [],
  "country_rules": [],
  "conflicts": []
}"""


# Universal fallback prompt optimized for investment guideline documents with tables and mixed formats
FALLBACK_SYSTEM_PROMPT = """You are an expert compliance analyst specializing in extracting investment rules from investment policy documents (Anlagerichtlinie, Investment Guidelines, Prospectus, etc.). Your task is to extract investment restrictions and permissions with maximum accuracy.

**DOCUMENT TYPE FOCUS:**
This is likely an investment guideline document that may contain:
- Tables with "Ja/Nein" (Yes/No), "Min", "Max", "Dimension" columns
- Hierarchical numbered sections (e.g., "2.1.4", "3.1", "4.2")
- Mixed formats: tables, paragraphs, bullet points, lists
- Evidence in both structured tables and descriptive text
- Sometimes empty fields in tables (this is normal - extract what's available)

**YOUR PRIMARY GOAL:**
Extract ALL investment instruments, sectors, and countries that are explicitly mentioned as ALLOWED or PROHIBITED, regardless of format (tables, text, lists, etc.).

**EXTRACTION APPROACH - HANDLE MULTIPLE FORMATS:**

**1. TABLE-BASED EXTRACTION (MOST COMMON):**
- Look for tables with columns like: "Ja/Nein", "Yes/No", "Allowed/Prohibited", "Min", "Max", "Dimension"
- Extract each row as a separate instrument rule
- "Ja" or "Yes" in the first column = ALLOWED (allowed=true)
- "Nein" or "No" in the first column = PROHIBITED (allowed=false)
- If "Min", "Max", or "Dimension" columns are empty, that's fine - still extract the instrument
- Include the table row content as evidence (e.g., "Ja/Nein: Ja, Max: 25%, Dimension: % des Fondsvermögens")
- If instrument name is in one column and status in another, match them correctly

**2. LIST-BASED EXTRACTION:**
- Look for sections titled "Zulässige Anlagen", "Permitted Investments", "Allowed Investments" → extract ALL items as allowed=true
- Look for sections titled "Unzulässige Anlagen", "Prohibited Investments", "Restricted Investments" → extract ALL items as allowed=false
- Extract each item in the list separately, even if comma-separated
- Include the section header and list content as evidence

**3. PARAGRAPH/TEXT-BASED EXTRACTION:**
- Look for statements like: "X is allowed", "Y is prohibited", "investments in Z are permitted"
- Extract instruments mentioned in descriptive paragraphs
- Look for restrictions in "Weitere Restriktionen" (Further Restrictions) sections
- Include the exact sentence or paragraph as evidence

**4. HIERARCHICAL STRUCTURE:**
- Pay attention to section numbers (e.g., "2.1.4", "3.1") - they indicate document structure
- Parent sections may apply to child sections (e.g., "Derivate: Ja" may apply to all derivative subtypes)
- But also check for specific rules in sub-sections that override general rules
- Extract rules from both parent and child sections

**HOW TO IDENTIFY ALLOWED ITEMS (MULTI-LANGUAGE):**
- German: "ja", "erlaubt", "zugelassen", "berechtigt", "darf", "zulässig"
- English: "allowed", "permitted", "authorized", "approved", "may invest", "can invest", "eligible"
- French: "autorisé", "permis", "approuvé"
- Spanish: "permitido", "autorizado", "aprobado"
- Table indicators: "Ja", "Yes", "X" marks, checkmarks, "✓"
- Positive statements: "the fund may invest in...", "investments in X are permitted"

**HOW TO IDENTIFY PROHIBITED ITEMS (MULTI-LANGUAGE):**
- German: "nein", "verboten", "nicht erlaubt", "ausgeschlossen", "darf nicht", "unzulässig"
- English: "prohibited", "forbidden", "not allowed", "restricted", "excluded", "may not invest"
- French: "interdit", "non autorisé", "exclu"
- Spanish: "prohibido", "no permitido", "excluido"
- Table indicators: "Nein", "No", "-" (dash), empty cells (in prohibited context)
- Negative statements: "the fund may not invest in...", "investments in X are not allowed"

**HANDLING EMPTY FIELDS:**
- If a table has "Ja/Nein: Ja" but "Min", "Max", "Dimension" are empty → still extract as allowed=true
- Empty fields don't mean "not allowed" - they just mean no specific limits are stated
- Only use "Nein" or explicit prohibition language to mark as allowed=false

**EVIDENCE EXTRACTION - BE THOROUGH:**
- **From Tables**: Include the table row content (e.g., "Ja/Nein: Ja, Max: 20%, Dimension: % des Fondsvermögens")
- **From Text**: Include the exact sentence or paragraph that states the rule
- **From Lists**: Include the section header and the list item (e.g., "Zulässige Anlagen: Aktien, Bezugsrechte")
- **From Hierarchical Sections**: Include section number and content (e.g., "Section 2.1.4: Renten - Aktienanleihen: Ja, Max: 10%")
- Always include enough context to make the rule clear (up to 300 characters)
- If evidence spans multiple formats (table + text), combine them

**WHAT TO EXTRACT:**
1. **Investment Instruments**: 
   - Bonds: Staatsanleihen, Unternehmensanleihen, Pfandbriefe, Covered Bonds, etc.
   - Stocks: Aktien, Common Stock, Preferred Stock, etc.
   - Derivatives: Futures, Options, Warrants, Swaps, Forwards, etc.
   - Funds: Aktienfonds, Rentenfonds, Geldmarktfonds, etc.
   - Certificates: Zertifikate, Certificates on indices, etc.
   - Others: Repos, Edelmetalle, Unternehmensbeteiligungen, etc.

2. **Sectors**: Energy, Healthcare, Defense, Tobacco, Weapons, Technology, Financial Services, etc.

3. **Countries/Regions**: Any geographic restrictions mentioned

**SPECIAL PATTERNS TO RECOGNIZE:**
- "Keine Restriktionen" (No Restrictions) = typically means allowed, but check context
- "Alle" (All) = typically means all items in category are allowed
- "Ausnahme" (Exception) = note the exception separately
- Percentage limits (e.g., "max 50% des Fondsvermögens") = include in evidence
- "pro Emittent" (per issuer) = include in evidence as it's a grouping rule

**IMPORTANT RULES:**
- Extract EVERY explicitly mentioned rule - don't skip any
- If you see a table with 30 rows, extract all 30 rows
- If you see a list with 20 items, extract all 20 items
- If an instrument appears in multiple places, extract each occurrence (may have different rules)
- Search the ENTIRE document systematically - rules can be in any section
- Don't assume - only extract what is explicitly stated

**OUTPUT FORMAT:**
Return ONLY valid JSON:
{
  "instrument_rules": [
    {"instrument": "exact name from document", "allowed": true/false, "reason": "exact quote including table row or text"}
  ],
  "sector_rules": [
    {"sector": "exact name from document", "allowed": true/false, "reason": "exact quote from document"}
  ],
  "country_rules": [
    {"country": "exact name from document", "allowed": true/false, "reason": "exact quote from document"}
  ],
  "conflicts": []
}

**CRITICAL**: Investment guideline documents almost always contain rules. If you find tables with "Ja/Nein" columns or lists of instruments, extract them. Returning empty arrays is only acceptable if the document truly contains NO investment rules at all."""


class LLMService:
    """Service for managing different LLM providers with fallback and validation"""
    
    def __init__(self):
        # Get API key - make it optional for graceful degradation
        api_key = os.getenv("OPENAI_API_KEY")
        
        # Initialize client only if API key is available
        self.client = None
        if api_key:
            try:
                # Create a custom httpx client without proxies to avoid compatibility issues
                # This prevents the "unexpected keyword argument 'proxies'" error
                # Use connection pooling for faster requests (reuse connections)
                http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(180.0, connect=15.0, read=180.0),  # 3 min timeout for large docs
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                    # Explicitly don't pass proxies parameter
                )
                
                # Initialize AsyncOpenAI client with custom http_client
                self.client = AsyncOpenAI(
                    api_key=api_key,
                    http_client=http_client
                )
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client: {str(e)}")
                logger.warning("OpenAI API key not found. Embedding generation will be disabled.")
                self.client = None
        else:
            logger.warning("OpenAI API key not found. Embedding generation will be disabled.")
        
        self.providers = {
            "openai": OpenAIProvider()
        }
        self.trace_handler = TraceHandler()
    
    def get_provider(self, provider_name: str) -> LLMProviderInterface:
        """Get LLM provider by name"""
        if provider_name not in self.providers:
            raise ValueError(f"Unknown provider: {provider_name}")
        return self.providers[provider_name]
    
    async def analyze_text(self, prompt_text: str) -> dict:
        """Analyze text using the new OpenAI client with robust system prompt"""
        if not self.client:
            return {"error": "OpenAI client not initialized. Please set OPENAI_API_KEY environment variable."}
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt_text}
                ]
            )
            raw = response.choices[0].message.content

            # try to parse JSON safely
            cleaned = raw.strip().strip("```json").strip("```")
            # Clean invalid control characters before parsing
            cleaned = _clean_json_string(cleaned)
            return json.loads(cleaned)

        except Exception as e:
            logger.error(f"LLM Error: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def analyze_document(self, text: str, provider: str, model: str, trace_id: Optional[str] = None) -> Dict:
        """Analyze document using new OpenAI client with robust system prompt"""
        if not self.client:
            raise ValueError("OpenAI client not initialized. Please set OPENAI_API_KEY environment variable.")
        
        # Calculate safe text limit based on model
        # GPT-4o/GPT-4o-mini: 128k tokens (~512k chars), GPT-5/GPT-5.1: 128k+ tokens
        # Note: gpt-4 check kept for backward compatibility but this model is deprecated
        if model == "gpt-4":
            # GPT-4 has 8192 token limit: reserve ~1200 for enhanced prompts, ~2000 for completion
            max_text_length = 10000  # Conservative limit for GPT-4's 8k context
        elif model == "gpt-5" or model == "gpt-5.1" or model == "gpt-5.2":
            # GPT-5/GPT-5.1/GPT-5.2 assumed to have large context window (128k+ tokens) - support very large files
            max_text_length = 1000000  # 1MB chars for very large documents (150+ pages)
        else:
            # Modern models (GPT-4o, GPT-4o-mini) have 128k context window (~512k chars)
            max_text_length = 500000  # 500k chars for large documents
        
        # For very large documents, we'll use section-based processing instead of truncating
        # Only truncate if absolutely necessary (old GPT-4 model)
        if model == "gpt-4" and len(text) > max_text_length:
            logger.warning(f"Document is {len(text)} chars, truncating to {max_text_length} for GPT-4 (deprecated model)")
            text_to_analyze = text[:max_text_length]
        else:
            # For modern models, process full text (will be chunked by section-based extraction)
            text_to_analyze = text
            if len(text) > max_text_length:
                logger.info(f"Large document ({len(text)} chars) - will use section-based chunking for analysis")
        
        # Detailed system prompt for extraction (used in user role for detailed instructions)
        extraction_system_prompt = f"""You are an expert compliance analyst analyzing an investment policy document (Verkaufsprospekt, Prospectus, or similar). Your PRIMARY goal is to achieve 100% accuracy by finding ALL items that are explicitly stated as ALLOWED or PERMITTED, and ALL items that are PROHIBITED.

**CRITICAL: HANDLING LONG DOCUMENTS (VERKAUFSPROSPEKT, PROSPECTUS, ETC.)**
This document may be very long (100+ pages). You MUST:
1. **Systematically process EVERY section** - do not skip any part of the document
2. **Search methodically**: Introduction → Investment Policy → Restrictions → Appendices → Tables → Footnotes
3. **Extract from ALL locations**: Rules can be in main text, tables, footnotes, appendices, sidebars, or any section
4. **For long documents, rules are often scattered** - you must search thoroughly through the entire document
5. **DO NOT return empty results** - if this is an investment policy document, it MUST contain rules. If you find rules, extract them. If you don't find explicit rules, check again more carefully.
6. **Long documents often have comprehensive lists** - when you see lists (especially under "Zulässige Anlagen" or "Unzulässige Anlagen"), extract EVERY single item
7. **Tables are critical in long documents** - extract every table row that contains investment rules, even if the table spans multiple pages

**ACCURACY FIRST - COMPLETENESS AND PRECISION:**
- Extract EVERY rule - do not miss any instrument, sector, or country mentioned
- Use EXACT quotes from the document as evidence (copy text verbatim, do not paraphrase)
- Verify completeness: count items in lists and ensure you extracted all of them
- Cross-reference sections to catch all mentions of the same rule
- If uncertain, include in conflicts rather than guessing
- **MANDATORY**: If the document contains investment rules, you MUST extract at least some rules - returning empty arrays is only acceptable if the document truly contains NO investment rules at all

**CRITICAL: GERMAN DOCUMENT PATTERNS - TABLE STRUCTURE (HIGHEST PRIORITY)**
Many German investment documents use a table format with "ja" (yes) and "nein" (no) columns. This is THE PRIMARY way to identify allowed/prohibited instruments:

**TABLE FORMAT RECOGNITION:**
- Look for tables with column headers: "ja", "nein", "Detailrestriktionen", or similar
- The table structure may appear as: "Instrument Name | nein | ja | Detailrestriktionen"
- Or in text format: "Aktien | nein: - | ja: X | Detailrestriktionen: ..."
- Or as a list: "Aktien: nein: -, ja: X"
- **CRITICAL**: Even if the table structure is broken in text extraction, look for patterns like:
  * "Instrument name" followed by "ja: X" or "nein: X"
  * "Instrument name" with "X" in the "ja" column position
  * Rows where you can identify which column is "ja" and which is "nein"

**INTERPRETATION RULES FOR TABLES:**
- An "X" (cross) mark in the "ja" column = ALLOWED (allowed=true) - THIS IS THE MOST IMPORTANT RULE
- An "X" (cross) mark in the "nein" column = NOT ALLOWED (allowed=false)
- A "✓" (checkmark) in the "ja" column = ALLOWED (allowed=true)
- A "-" (hyphen/dash) in either column typically means NOT ALLOWED
- **CRITICAL**: If you see "ja: X" or "X" in the "ja" column position → that instrument is ALLOWED
- **CRITICAL**: If you see "nein: X" or "X" in the "nein" column position → that instrument is NOT ALLOWED
- **MOST IMPORTANT**: Extract EVERY row from these tables - count the rows and extract all of them

**OTHER GERMAN PATTERNS:**
- "ja" = yes/allowed, "nein" = no/not allowed
- "erlaubt", "zugelassen", "berechtigt", "darf" = allowed/permitted
- "verboten", "nicht erlaubt", "ausgeschlossen", "darf nicht" = prohibited/not allowed
- Examples in text: "FX Forwards X", "Derivatives (X)", "Options: -", "Bonds -", "Aktien ✓"

**CRITICAL: GERMAN SECTION HEADERS WITH LISTS**
When you see these German section headers, you MUST extract EVERY item in the list that follows:
- "Zulässige Anlagen" or "Zulässige Anlageinstrumente" = Permitted Investments → Extract EVERY item in the list as allowed=true
- "Erlaubte Anlagen" or "Erlaubte Instrumente" = Permitted Investments → Extract EVERY item in the list as allowed=true
- "Zugelassene Anlagen" or "Zugelassene Instrumente" = Permitted Investments → Extract EVERY item in the list as allowed=true
- "Unzulässige Anlagen" or "Unzulässige Anlageinstrumente" = Prohibited Investments → Extract EVERY item in the list as allowed=false
- These lists can be formatted as: bullet points (•, -, *), numbered lists (1., 2., 3.), comma-separated items, table rows, or paragraph text
- Each item in the list is a separate instrument that must be extracted individually
- **VERIFICATION**: Count the items in the list and ensure you extract that exact number - if you see 30 items, extract all 30
- **COMMON PATTERNS**: These sections often appear in: main investment policy section, appendices (Anhänge), supplementary documents (Beilagen), or tables
- Example: If you see "Zulässige Anlagen: Aktien, Bezugsrechte, Schatzanweisungen, Anleihen, Pfandbriefe" → extract 5 separate rules, one for each instrument
- Example: If you see a table with 25 rows under "Zulässige Anlagen" header → extract all 25 rows as allowed=true

**SYSTEMATIC EXTRACTION PROCESS:**

**DEFAULT ASSUMPTION: All instruments are NOT ALLOWED (prohibited) unless explicitly stated as allowed/permitted**

**STEP 1: IDENTIFY TABLE STRUCTURE FIRST (CRITICAL)**
Before extracting instruments, identify if the document contains tables with "ja/nein" columns:
- Look for patterns like: "Instrument | nein | ja | Detailrestriktionen"
- Look for patterns like: "Aktien | nein: - | ja: X"
- Look for patterns like: "Aktien: nein: -, ja: X"
- Look for column headers: "ja", "nein", "Detailrestriktionen"
- **IF YOU FIND SUCH A TABLE**: This is the PRIMARY source of rules - extract EVERY row from it
- **IF YOU FIND SUCH A TABLE**: The "X" marks in the "ja" column indicate ALLOWED instruments
- **IF YOU FIND SUCH A TABLE**: Count the rows and extract ALL of them - do not skip any

**STEP 2: EXTRACT ALL INSTRUMENTS MENTIONED IN THE DOCUMENT**
- Extract every instrument, sector, and country mentioned in the document
- Default status: allowed=false (prohibited) unless you find explicit evidence otherwise
- Use exact instrument names from the document
- Extract from all sections: main text, tables, footnotes, appendices
- **PRIORITY**: If you found a table structure in Step 1, extract from that table FIRST

**STEP 3: SEARCH FOR EXPLICITLY ALLOWED ITEMS (BE VERY THOROUGH!)**
When you find explicit evidence that an instrument is ALLOWED, mark it as allowed=true. Search for:

**A. TABLES WITH "ja/nein" COLUMNS (HIGHEST PRIORITY - MOST COMMON FORMAT):**
- **THIS IS THE PRIMARY FORMAT** - Look for tables with columns: "ja" (yes), "nein" (no), "Detailrestriktionen" (detailed restrictions)
- Table structure may appear as:
  * Structured table: "Instrument | nein | ja | Detailrestriktionen"
  * Text format: "Aktien | nein: - | ja: X | Detailrestriktionen: ..."
  * List format: "Aktien: nein: -, ja: X"
  * Broken table: "Aktien" followed by "ja: X" somewhere in the same area
- **CRITICAL RULE**: If "ja" column has "X" mark → that instrument is ALLOWED (allowed=true)
- **CRITICAL RULE**: If "ja" column has "✓" or checkmark → that instrument is ALLOWED (allowed=true)
- **CRITICAL RULE**: If you see "X" in the "ja" column position → that instrument is ALLOWED (allowed=true)
- **CRITICAL**: Extract EVERY row from these tables - count rows and extract all of them
- **CRITICAL**: Even if table structure is broken in text, look for patterns like "Instrument name" + "ja: X"
- **VERIFICATION**: If you see a table with 30 rows, extract all 30 rows - do not skip any

**EXAMPLE OF TABLE EXTRACTION:**
If you see a table like this:
```
Aktien | nein: - | ja: X | Detailrestriktionen: ...
Bezugsrechte | nein: - | ja: X | Detailrestriktionen: ...
Staatsanleihen | nein: - | ja: X | Detailrestriktionen: ...
Pfandbriefe | nein: - | ja: X | Detailrestriktionen: ...
ABS/MBS/CDO/CLO | nein: X | ja: - | Detailrestriktionen: ...
```

You MUST extract:
- {{"instrument": "Aktien", "allowed": true, "reason": "X mark in 'ja' column"}}
- {{"instrument": "Bezugsrechte", "allowed": true, "reason": "X mark in 'ja' column"}}
- {{"instrument": "Staatsanleihen", "allowed": true, "reason": "X mark in 'ja' column"}}
- {{"instrument": "Pfandbriefe", "allowed": true, "reason": "X mark in 'ja' column"}}
- {{"instrument": "ABS/MBS/CDO/CLO", "allowed": false, "reason": "X mark in 'nein' column"}}

**CRITICAL**: Extract ALL rows, not just a few!

**B. GERMAN SECTION HEADERS:**
- "Zulässige Anlagen" or "Zulässige Anlageinstrumente" = Permitted Investments
- "Erlaubte Anlagen" or "Erlaubte Instrumente" = Permitted Investments  
- "Zugelassene Anlagen" or "Zugelassene Instrumente" = Permitted Investments
- When you see ANY of these headers, the list that follows contains ALLOWED instruments
- Extract EVERY single item from these lists as allowed=true
- These lists can be formatted as: bullet points, numbered lists, comma-separated, table rows, or paragraph text
- **VERIFICATION**: Count the items in the list - if you see 20 items, extract all 20, not just a few

**C. EXPLICIT LANGUAGE:**
- English: "allowed", "permitted", "authorized", "approved", "may invest", "can invest", "eligible", "can be invested"
- German: "erlaubt", "zugelassen", "berechtigt", "darf", "ja", "zulässig", "darf investiert werden", "kann investiert werden"
- Phrases: "investments are permitted in...", "the fund may invest in...", "investments in X are allowed", "der Fonds darf in X investieren"

**D. "X" MARKS IN ANY CONTEXT:**
- An "X" mark next to an instrument name means ALLOWED (allowed=true)
- Can appear in: tables, lists, inline text, checkboxes, or any format
- Examples: "Aktien X", "Derivatives (X)", "Options: X", table cell with "X"

**E. COMPREHENSIVE LISTS:**
- Look for long lists of instruments - these are often the main source of allowed items
- Even if the list doesn't have an explicit header, if it's in a section about permitted investments, extract all items
- Check appendices, footnotes, and supplementary sections - allowed lists are often there

**CRITICAL REMINDERS:**
- Be VERY thorough - long documents often have 20-50+ allowed instruments
- Don't stop after finding a few items - continue searching the entire document
- Tables are especially important - extract every row that shows an instrument as allowed
- If you find a "Zulässige Anlagen" section with many items, extract ALL of them individually

**STEP 4: SEARCH FOR EXPLICITLY PROHIBITED ITEMS**
When you find explicit evidence that an instrument is PROHIBITED, mark it as allowed=false:
- "prohibited", "forbidden", "not allowed", "restricted", "excluded", "may not invest", "not eligible"
- German: "verboten", "nicht erlaubt", "ausgeschlossen", "darf nicht", "nein", "unzulässig"
- A "-" (hyphen) mark in any context (tables, lists, inline text - German style)
- "investments in X are not allowed", "prohibited from investing in..."
- **CRITICAL**: When you see "Unzulässige Anlagen" section, extract EVERY single item in that list as allowed=false - verify you got them all

**STEP 5: HANDLE CONDITIONAL RULES**
If a rule has conditions, extract it with allowed=true but include the condition in the reason:
- "subject to", "provided that", "up to X%", "with restrictions", "under certain conditions"
- Example: "FX Forwards allowed up to 10% of portfolio" → {{"instrument": "FX Forwards", "allowed": true, "reason": "FX Forwards allowed up to 10% of portfolio"}}
- Example: "Derivatives permitted subject to risk limits" → {{"instrument": "Derivatives", "allowed": true, "reason": "Derivatives permitted subject to risk limits"}}

**CRITICAL: DEFAULT BEHAVIOR**
- Default assumption: All instruments are NOT ALLOWED (allowed=false) unless explicitly stated as allowed/permitted
- Extract all instruments mentioned in the document
- If you find explicit evidence that an instrument is allowed (e.g., in "Zulässige Anlagen" list, or "X" mark in "ja" column), mark it as allowed=true
- If you find explicit evidence that an instrument is prohibited (e.g., in "Unzulässige Anlagen" list, or "-" mark), mark it as allowed=false
- If an instrument is mentioned but you cannot find explicit "allowed" or "prohibited" language, keep it as allowed=false (default assumption)

**STEP 6: CHECK FOR CONFLICTS**
- If the same instrument appears as both allowed and prohibited in different sections → add to conflicts
- If rules are ambiguous or contradictory → add to conflicts with explanation
- If you find unclear statements → add to conflicts rather than guessing

**INSTRUMENT NAME RECOGNITION:**
Recognize these as the SAME instrument types (but use the EXACT name from document):
- "FX Forwards" = "forex forwards" = "foreign exchange forwards" = "FX" = "forex" = "Foreign Exchange Forwards"
- "currency futures" = "FX futures" = "foreign exchange futures" = "forex futures" = "Currency Futures"
- "derivatives" includes: options, futures, forwards, swaps, warrants, structured products
- German terms: "Aktien" = stocks/shares, "Anleihen" = bonds, "Schatzanweisungen" = treasury bills, "Bezugsrechte" = subscription rights, "Pfandbriefe" = covered bonds, etc.
- **CRITICAL FOR INDEX FUTURES/OPTIONS**: Any variant of "index future" (e.g., "equity index future", "equity index futures", "Aktienindexfutures") should be treated as "index future" for rule matching. Any variant of "index option" (e.g., "equity index option", "equity index options", "Aktienindexoptionen") should be treated as "index option" for rule matching. Extract the exact name from the document, but the system will map it to the base category.
- **IMPORTANT**: Use the EXACT name as it appears in the document - do not translate unless the document itself uses both languages

**WHAT TO EXTRACT:**
- **Sectors**: Energy, Healthcare, Defense, Tobacco, Weapons, Technology, Financial Services, etc.
- **Countries**: USA, China, Russia, Europe, UK, Germany, France, etc. (use exact country names from document)
- **Instruments**: Use EXACT names from document (e.g., "FX Forwards", "currency futures", "covered bonds", "common stock", "Aktien", "Bezugsrechte", "Schatzanweisungen", etc.)
- **CRITICAL**: Extract each instrument individually - do not group them together
- **CRITICAL FOR TABLES**: Extract every table row, including nested/sub-items, as separate entries. Do not skip any rows.
- **🔴 SWAPS**: If "Swaps" is mentioned anywhere in the document, ALWAYS extract as: {{"instrument": "Swaps", "allowed": false, "reason": "Swaps are always prohibited"}} - No checking needed, always not allowed

**EVIDENCE REQUIREMENTS:**
- The "reason" field must contain the EXACT quote from the document (verbatim copy)
- Include enough context to make the rule clear
- If rule spans multiple sentences, include all relevant parts
- Minimum: include the sentence containing the rule
- Maximum: 300 characters (but prioritize completeness over length limit)

**COMPLETENESS VERIFICATION (MANDATORY BEFORE FINISHING):**
Before finishing, you MUST verify:
1. Did you check ALL sections of the document? (main text, tables, footnotes, appendices, introduction, investment policy, restrictions)
2. Did you extract ALL items from lists under "Zulässige Anlagen" and "Unzulässige Anlagen"?
3. Did you extract ALL rows from tables (including nested items, multi-page tables)?
4. Did you check for both allowed AND prohibited statements throughout the ENTIRE document?
5. Did you use exact quotes as evidence?
6. **CRITICAL**: Did you search systematically through the entire document, or did you only check the beginning?
7. **CRITICAL**: If this is a long document (Verkaufsprospekt/Prospectus), did you check sections that might be later in the document?
8. **CRITICAL**: Are you returning empty results? If yes, double-check - investment policy documents almost always contain rules. Search more carefully.
9. **🚨 MANDATORY FUTURES/OPTIONS VALIDATION**: For EVERY future and option you extracted:
   - Did you check for explicit prohibitions FIRST (before marking as allowed)?
   - If you marked a future/option as allowed=true, did you verify it's NOT prohibited (no "-", no "nein", not in prohibited section)?
   - Did you check the SPECIFIC "Futures" or "Options" row in tables (not just "Derivatives" row)?
   - Did you find explicit allowance evidence (not just assumed from "Derivatives" rule)?
   - If "Derivatives: X" but "Futures: -" exists, did you mark Futures as allowed=false?

**IF YOU ARE RETURNING EMPTY RESULTS:**
- STOP and re-examine the document
- Look for sections titled: "Investment Policy", "Investment Restrictions", "Zulässige Anlagen", "Unzulässige Anlagen", "Permitted Investments", "Prohibited Investments", "Investment Guidelines", "Anlagegrundsätze"
- Check tables - even if they seem unrelated, they may contain investment rules
- Look for lists of instruments, sectors, or countries
- Search for keywords: "erlaubt", "zugelassen", "verboten", "nicht erlaubt", "allowed", "permitted", "prohibited", "forbidden"
- If you still find nothing, include a conflict explaining why no rules were found

**CRITICAL RULES WITH EXAMPLES:**
1. If document says "FX Forwards are allowed" → extract: {{"instrument": "FX Forwards", "allowed": true, "reason": "FX Forwards are allowed"}}
2. If document says "currency futures are permitted" → extract: {{"instrument": "currency futures", "allowed": true, "reason": "currency futures are permitted"}}
3. If document has a section "Zulässige Anlagen" with a list of 20 items → extract 20 separate instrument rules, one for each item (verify you got all 20)
4. If document has a section "Unzulässige Anlagen" with a list of 15 items → extract 15 separate instrument rules, one for each item (verify you got all 15)
5. DO NOT mark something as "not allowed" unless explicitly prohibited - if not mentioned, do not include it
6. Search ENTIRE document systematically - rules can be in any section, table, footnote, or appendix
7. **DO NOT SKIP ITEMS IN LISTS - extract every single instrument mentioned**
8. **CRITICAL FOR TABLES: Include every table row, even nested/sub-items, as a separate entry. Extract each row individually - do not skip any rows in tables.**
9. If a table has 50 rows, extract 50 separate rules - count them to verify

**Return JSON only (no explanations, no markdown, just valid JSON):**
{{
  "sector_rules": [{{"sector": "string", "allowed": true/false, "reason": "exact quote from document"}}],
  "country_rules": [{{"country": "string", "allowed": true/false, "reason": "exact quote from document"}}],
  "instrument_rules": [{{"instrument": "string", "allowed": true/false, "reason": "exact quote from document"}}],
  "conflicts": [{{"category": "string", "detail": "string describing the conflict"}}]
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

**Document text to analyze (search through ALL of it systematically, section by section):**
{text_to_analyze}"""

        if trace_id:
            prompt_data = {
                "model": model,
                "temperature": 0,
                "timestamp": time.time(),
                "trace_id": trace_id,
                "provider": provider,
                "text_length": len(text),
                "text_preview": text[:500] + "..." if len(text) > 500 else text,
                "system_prompt": SYSTEM_PROMPT,
                "extraction_system_prompt": extraction_system_prompt
            }
            await self.trace_handler.save_llm_prompt(trace_id, prompt_data)

        try:
            # Use new OpenAI client approach with optimized settings for speed
            # GPT-4 has 8k context window, enhanced prompts are longer, so reduce max_tokens further
            # Reserve ~2000 tokens for completion to leave room for input (~5500 tokens with enhanced prompts)
            api_params = {
                "model": model,
                "top_p": 1,  # Conservative mode
                "presence_penalty": 0,  # No penalty for presence
                "frequency_penalty": 0,  # No penalty for frequency
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": extraction_system_prompt}
                ]
            }
            
            # Set temperature based on model requirements
            # gpt-5/gpt-5.1/gpt-5.2 only supports default temperature (1), not 0
            if model == "gpt-5" or model == "gpt-5.1" or model == "gpt-5.2":
                # gpt-5/gpt-5.1/gpt-5.2 requires default temperature (1)
                api_params["temperature"] = 1
            else:
                # Other models can use temperature 0 for deterministic responses
                api_params["temperature"] = 0  # Deterministic, evidence-based mode
            
            # Use correct parameter based on model
            # GPT-5/5.1/5.2 require max_completion_tokens (newer models)
            # Older models use max_tokens
            if model in ["gpt-5", "gpt-5.1", "gpt-5.2"]:
                # GPT-5/5.1/5.2 have large context windows - use higher limit to avoid truncation
                api_params["max_completion_tokens"] = 8000
            elif model in ["o1", "o1-mini", "o1-preview", "o1-2024-09-12", "gpt-4.1"]:
                api_params["max_completion_tokens"] = 4000
            else:
                # Standard models use max_tokens
                # Increased to 4000 to avoid truncation (costs more but ensures completeness)
                # GPT-4 has 8k context, but we'll use 3500 to leave room for input
                api_params["max_tokens"] = 3500 if model == "gpt-4" else 4000
            
            response = await self.client.chat.completions.create(**api_params)
            raw = response.choices[0].message.content

            # Save raw LLM response to trace file (before parsing to rule out parser errors)
            if trace_id:
                trace_dir = self.trace_handler.get_trace_dir(trace_id)
                os.makedirs(trace_dir, exist_ok=True)
                raw_response_path = os.path.join(trace_dir, f"{trace_id}_llm_raw.txt")
                with open(raw_response_path, 'w', encoding='utf-8') as f:
                    f.write(raw)

            # Parse JSON safely - extract JSON from response (handle extra text)
            cleaned = raw.strip().strip("```json").strip("```").strip()
            
            # Find first { and last } to extract JSON even if there's extra text
            json_start = cleaned.find('{')
            json_end = cleaned.rfind('}') + 1
            
            if json_start == -1 or json_end <= json_start:
                logger.error(f"❌ No valid JSON found in LLM response")
                logger.error(f"❌ Full response (first 2000 chars): {cleaned[:2000]}")
                logger.error(f"❌ Full response length: {len(cleaned)} chars")
                logger.error(f"❌ Response contains '{{': {cleaned.find('{') != -1}")
                logger.error(f"❌ Response contains '}}': {cleaned.find('}') != -1}")
                logger.error(f"❌ Response contains '[': {cleaned.find('[') != -1}")
                # Try to find JSON array instead
                array_start = cleaned.find('[')
                array_end = cleaned.rfind(']') + 1
                if array_start != -1 and array_end > array_start:
                    logger.warning(f"⚠️ Found JSON array instead of object, trying to parse...")
                    try:
                        array_str = cleaned[array_start:array_end]
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
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ Failed to parse JSON array: {e}")
                raise ValueError(f"LLM response does not contain valid JSON. Response preview: {cleaned[:500]}")
            
            json_str = cleaned[json_start:json_end]
            # Clean invalid control characters before parsing
            json_str = _clean_json_string(json_str)
            result = json.loads(json_str)
            
            # Validate and return
            validated_result = self._validate_result(result)
            
            if trace_id:
                await self.trace_handler.save_llm_response(trace_id, {
                    "provider": provider,
                    "model": model,
                    "result": validated_result,
                    "timestamp": time.time(),
                    "trace_id": trace_id,
                    "success": True
                })
            
            return validated_result
            
        except Exception as e:
            err_msg = str(e).lower()
            
            # Handle model not available - try fallback models
            if "404" in err_msg or "does not exist" in err_msg:
                logger.warning(f"Model '{model}' unavailable. Falling back to 'gpt-4o'")
                try:
                    fallback_params = {
                        "model": "gpt-4o",
                        "temperature": 0,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": extraction_system_prompt}
                        ]
                    }
                    # gpt-4o uses max_tokens, not max_completion_tokens
                    fallback_params["max_tokens"] = 4000
                    response = await self.client.chat.completions.create(**fallback_params)
                    raw = response.choices[0].message.content
                    
                    # Save raw LLM response to trace file (fallback model)
                    if trace_id:
                        trace_dir = self.trace_handler.get_trace_dir(trace_id)
                        os.makedirs(trace_dir, exist_ok=True)
                        raw_response_path = os.path.join(trace_dir, f"{trace_id}_llm_raw.txt")
                        with open(raw_response_path, 'w', encoding='utf-8') as f:
                            f.write(raw)
                    
                    cleaned = raw.strip().strip("```json").strip("```")
                    # Clean invalid control characters before parsing
                    cleaned = _clean_json_string(cleaned)
                    result = json.loads(cleaned)
                    return self._validate_result(result)
                except Exception as inner_e:
                    logger.warning("gpt-4o also failed, falling back to 'gpt-4o-mini'")
                    fallback_params = {
                        "model": "gpt-4o-mini",
                        "temperature": 0,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": extraction_system_prompt}
                        ]
                    }
                    # gpt-4o-mini uses max_tokens, not max_completion_tokens
                    fallback_params["max_tokens"] = 4000
                    response = await self.client.chat.completions.create(**fallback_params)
                    raw = response.choices[0].message.content
                    
                    # Save raw LLM response to trace file (fallback model)
                    if trace_id:
                        trace_dir = self.trace_handler.get_trace_dir(trace_id)
                        os.makedirs(trace_dir, exist_ok=True)
                        raw_response_path = os.path.join(trace_dir, f"{trace_id}_llm_raw.txt")
                        with open(raw_response_path, 'w', encoding='utf-8') as f:
                            f.write(raw)
                    
                    cleaned = raw.strip().strip("```json").strip("```")
                    # Clean invalid control characters before parsing
                    cleaned = _clean_json_string(cleaned)
                    result = json.loads(cleaned)
                    return self._validate_result(result)
            
            if trace_id:
                await self.trace_handler.save_llm_response(trace_id, {
                    "provider": provider,
                    "model": model,
                    "error": str(e),
                    "timestamp": time.time(),
                    "trace_id": trace_id,
                    "success": False
                })
            
            raise e

    async def analyze_document_fallback(self, text: str, provider: str, model: str, trace_id: Optional[str] = None) -> Dict:
        """
        Fallback analysis method using universal prompt for documents that don't match German-specific patterns.
        This is used when the primary analysis returns 0 instrument rules.
        """
        if not self.client:
            raise ValueError("OpenAI client not initialized. Please set OPENAI_API_KEY environment variable.")
        
        # Calculate safe text limit based on model (same as primary method)
        if model == "gpt-4":
            max_text_length = 10000
        elif model == "gpt-5" or model == "gpt-5.1" or model == "gpt-5.2":
            max_text_length = 1000000
        else:
            max_text_length = 500000
        
        if model == "gpt-4" and len(text) > max_text_length:
            logger.warning(f"Document is {len(text)} chars, truncating to {max_text_length} for GPT-4 (deprecated model)")
            text_to_analyze = text[:max_text_length]
        else:
            text_to_analyze = text
            if len(text) > max_text_length:
                logger.info(f"Large document ({len(text)} chars) - will use section-based chunking for analysis")
        
        # Enhanced fallback prompt optimized for investment guideline documents
        fallback_prompt = f"""You are analyzing an investment guideline document (Anlagerichtlinie, Investment Guidelines, Prospectus, etc.). Extract ALL investment rules (instruments, sectors, countries) that are explicitly stated as ALLOWED or PROHIBITED.

**CRITICAL INSTRUCTIONS:**
1. Search through the ENTIRE document systematically - check all sections, tables, lists, and paragraphs
2. This document likely contains TABLES with "Ja/Nein" columns - extract EVERY row from these tables
3. Look for hierarchical sections (numbered like "2.1.4", "3.1") - extract rules from both parent and child sections
4. Extract EVERY rule you find - if you see a table with 30 rows, extract all 30 rows
5. Use the EXACT names and quotes from the document
6. If "Min", "Max", or "Dimension" columns are empty, still extract the instrument if "Ja/Nein" has a value

**TABLE EXTRACTION (HIGHEST PRIORITY):**
- Look for tables with columns: "Ja/Nein", "Yes/No", "Min", "Max", "Dimension"
- "Ja" or "Yes" = ALLOWED (allowed=true)
- "Nein" or "No" = PROHIBITED (allowed=false)
- Extract each table row as a separate instrument rule
- Include table row content in evidence (e.g., "Ja/Nein: Ja, Max: 25%, Dimension: % des Fondsvermögens")

**LIST EXTRACTION:**
- "Zulässige Anlagen" / "Permitted Investments" → extract ALL items as allowed=true
- "Unzulässige Anlagen" / "Prohibited Investments" → extract ALL items as allowed=false
- Extract each list item separately

**TEXT EXTRACTION:**
- Look for statements: "X is allowed", "Y is prohibited", "investments in Z are permitted"
- Check "Weitere Restriktionen" (Further Restrictions) sections
- Include exact sentences/paragraphs as evidence

**ALLOWED indicators (multi-language):**
- German: "ja", "erlaubt", "zugelassen", "berechtigt", "darf", "zulässig"
- English: "allowed", "permitted", "authorized", "approved", "may invest", "can invest", "eligible"
- Table: "Ja", "Yes", "X" marks, checkmarks

**PROHIBITED indicators (multi-language):**
- German: "nein", "verboten", "nicht erlaubt", "ausgeschlossen", "darf nicht", "unzulässig"
- English: "prohibited", "forbidden", "not allowed", "restricted", "excluded", "may not invest"
- Table: "Nein", "No", "-" (dash)

**SPECIAL PATTERNS:**
- "Keine Restriktionen" (No Restrictions) = typically allowed
- "Alle" (All) = typically all items allowed
- Percentage limits (e.g., "max 50% des Fondsvermögens") = include in evidence

**Document text to analyze:**
{text_to_analyze}

Return ONLY valid JSON:
{{
  "instrument_rules": [{{"instrument": "exact name from document", "allowed": true/false, "reason": "exact quote including table row or text"}}],
  "sector_rules": [{{"sector": "exact name from document", "allowed": true/false, "reason": "exact quote from document"}}],
  "country_rules": [{{"country": "exact name from document", "allowed": true/false, "reason": "exact quote from document"}}],
  "conflicts": []
}}"""

        if trace_id:
            prompt_data = {
                "model": model,
                "temperature": 0,
                "timestamp": time.time(),
                "trace_id": trace_id,
                "provider": provider,
                "text_length": len(text),
                "text_preview": text[:500] + "..." if len(text) > 500 else text,
                "system_prompt": FALLBACK_SYSTEM_PROMPT,
                "method": "fallback"
            }
            await self.trace_handler.save_llm_prompt(trace_id, prompt_data)

        try:
            api_params = {
                "model": model,
                "top_p": 1,
                "presence_penalty": 0,
                "frequency_penalty": 0,
                "messages": [
                    {"role": "system", "content": FALLBACK_SYSTEM_PROMPT},
                    {"role": "user", "content": fallback_prompt}
                ]
            }
            
            # Set temperature based on model requirements
            if model == "gpt-5" or model == "gpt-5.1" or model == "gpt-5.2":
                api_params["temperature"] = 1
            else:
                api_params["temperature"] = 0
            
            # Use correct parameter based on model
            # GPT-5/5.1/5.2 require max_completion_tokens (newer models)
            if model in ["gpt-5", "gpt-5.1", "gpt-5.2"]:
                api_params["max_completion_tokens"] = 8000
            elif model in ["o1", "o1-mini", "o1-preview", "o1-2024-09-12", "gpt-4.1"]:
                api_params["max_completion_tokens"] = 4000
            else:
                api_params["max_tokens"] = 3500 if model == "gpt-4" else 4000
            
            logger.info(f"🔄 Using fallback prompt (universal/language-agnostic) for analysis")
            response = await self.client.chat.completions.create(**api_params)
            raw = response.choices[0].message.content

            # Save raw LLM response to trace file
            if trace_id:
                trace_dir = self.trace_handler.get_trace_dir(trace_id)
                os.makedirs(trace_dir, exist_ok=True)
                raw_response_path = os.path.join(trace_dir, f"{trace_id}_llm_raw_fallback.txt")
                with open(raw_response_path, 'w', encoding='utf-8') as f:
                    f.write(raw)

            # Parse JSON safely
            cleaned = raw.strip().strip("```json").strip("```").strip()
            
            # Find first { and last } to extract JSON even if there's extra text
            json_start = cleaned.find('{')
            json_end = cleaned.rfind('}') + 1
            
            if json_start == -1 or json_end <= json_start:
                logger.error(f"❌ No valid JSON found in fallback LLM response")
                logger.error(f"❌ Full response (first 2000 chars): {cleaned[:2000]}")
                raise ValueError(f"LLM fallback response does not contain valid JSON. Response preview: {cleaned[:500]}")
            
            json_str = cleaned[json_start:json_end]
            json_str = _clean_json_string(json_str)
            result = json.loads(json_str)
            
            # Validate and return
            validated_result = self._validate_result(result)
            
            if trace_id:
                await self.trace_handler.save_llm_response(trace_id, {
                    "provider": provider,
                    "model": model,
                    "result": validated_result,
                    "timestamp": time.time(),
                    "trace_id": trace_id,
                    "success": True,
                    "method": "fallback"
                })
            
            logger.info(f"✅ Fallback analysis complete: {len(validated_result.get('instrument_rules', []))} instrument rules extracted")
            return validated_result
            
        except Exception as e:
            logger.error(f"Fallback analysis error: {e}", exc_info=True)
            if trace_id:
                await self.trace_handler.save_llm_response(trace_id, {
                    "provider": provider,
                    "model": model,
                    "error": str(e),
                    "timestamp": time.time(),
                    "trace_id": trace_id,
                    "success": False,
                    "method": "fallback"
                })
            raise e

    async def analyze_document_with_tracing(self, text: str, provider: str, model: str, trace_id: str) -> Dict:
        """Analyze document with forensic tracing and validation"""
        provider_instance = self.get_provider(provider)
        messages = await self._get_llm_messages(provider_instance, text, model)

        prompt_data = {
            "model": model,
            "temperature": 0.1,
            "timestamp": time.time(),
            "trace_id": trace_id,
            "provider": provider,
            "text_length": len(text),
            "text_preview": text[:500] + "..." if len(text) > 500 else text,
            "messages": messages
        }
        await self.trace_handler.save_llm_prompt(trace_id, prompt_data)

        try:
            result = await provider_instance.analyze_document(text, model)
            validated = self._validate_result(result)
            await self.trace_handler.save_llm_response(trace_id, {
                "provider": provider,
                "model": model,
                "result": validated,
                "timestamp": time.time(),
                "trace_id": trace_id,
                "success": True
            })
            return validated

        except Exception as e:
            await self.trace_handler.save_llm_response(trace_id, {
                "provider": provider,
                "model": model,
                "error": str(e),
                "timestamp": time.time(),
                "trace_id": trace_id,
                "success": False
            })
            raise e
    
    def get_ollama_models(self) -> List[str]:
        """Get available Ollama models"""
        try:
            return self.providers["ollama"].get_available_models()
        except Exception:
            return []
    
    def get_openai_models(self) -> List[str]:
        """Get available OpenAI models"""
        # Return models from the provider's priority list (removed deprecated models)
        return self.providers["openai"].get_available_models()
    
    def _image_to_base64(self, image) -> str:
        """Convert PIL Image to base64 string for API"""
        import io
        from PIL import Image
        
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return img_str
    
    def _find_poppler_path(self) -> Optional[str]:
        """
        Try to find Poppler installation path.
        
        Returns:
            Path to Poppler bin directory if found, None otherwise
        """
        import os
        import subprocess
        
        # Common Windows installation paths
        possible_paths = [
            os.path.expanduser(r"~\poppler\poppler-24.08.0\Library\bin"),
            os.path.expanduser(r"~\poppler\Library\bin"),
            r"C:\poppler\Library\bin",
            r"C:\Program Files\poppler\Library\bin",
        ]
        
        # Check if pdftoppm is in PATH
        try:
            subprocess.run(['pdftoppm', '-v'], capture_output=True, check=True, timeout=2)
            return None  # Poppler is in PATH
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass
        
        # Check common installation paths
        for path in possible_paths:
            if os.path.exists(path):
                pdftoppm_path = os.path.join(path, 'pdftoppm.exe')
                if os.path.exists(pdftoppm_path):
                    return path
        
        return None
    
    def pdf_to_images(self, pdf_path: str):
        """
        Convert PDF pages to images.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of PIL Image objects
            
        Raises:
            ValueError: If pdf2image is not installed
            Exception: If Poppler is not available or conversion fails
        """
        if not PDF2IMAGE_AVAILABLE:
            raise ValueError(
                "pdf2image not available. Install it with: pip install pdf2image\n"
                "Note: pdf2image also requires Poppler to be installed on your system.\n"
                "Windows: Download from https://github.com/oschwartz10612/poppler-windows/releases\n"
                "Or use: conda install -c conda-forge poppler"
            )
        
        # Try to find Poppler path
        poppler_path = self._find_poppler_path()
        
        try:
            # Convert PDF to images with 200 DPI (good balance between quality and file size)
            if poppler_path:
                logger.info(f"Using Poppler from: {poppler_path}")
                return convert_from_path(pdf_path, dpi=200, poppler_path=poppler_path)
            else:
                return convert_from_path(pdf_path, dpi=200)
        except Exception as e:
            error_msg = str(e).lower()
            if "poppler" in error_msg or "pdftoppm" in error_msg or "not found" in error_msg:
                raise ValueError(
                    f"Poppler is required for PDF to image conversion but was not found.\n"
                    f"Error: {str(e)}\n\n"
                    f"Install Poppler:\n"
                    f"  Windows: Download from https://github.com/oschwartz10612/poppler-windows/releases\n"
                    f"           Extract to ~/poppler/ and the code will auto-detect it\n"
                    f"           Or extract and add the 'bin' folder to your PATH\n"
                    f"  Or use: conda install -c conda-forge poppler\n"
                    f"  Linux: sudo apt-get install poppler-utils\n"
                    f"  macOS: brew install poppler"
                ) from e
            raise
    
    async def analyze_document_vision(self, pdf_path: str, provider: str, model: str, trace_id: Optional[str] = None) -> Dict:
        """
        Analyze image-only PDF using vision models.
        
        This method converts PDF pages to images and uses GPT-5.2 with vision
        to read tables and extract investment rules, especially for German documents
        with "nein | ja | Detailrestriktionen" table format.
        
        Args:
            pdf_path: Path to PDF file
            provider: LLM provider (e.g., "openai")
            model: Model name (will be forced to "gpt-5.2" for vision analysis)
            trace_id: Optional trace ID for debugging
            
        Returns:
            Dict with same structure as analyze_document (instrument_rules, sector_rules, etc.)
        """
        if not self.client:
            raise ValueError("OpenAI client not initialized. Please set OPENAI_API_KEY environment variable.")
        
        if not PDF2IMAGE_AVAILABLE:
            raise ValueError("pdf2image not available. Install it with: pip install pdf2image")
        
        # Force use of GPT-5.2 for vision analysis
        vision_model = "gpt-5.2"
        logger.info(f"Using {vision_model} for vision analysis (requested model: {model} was overridden)")
        
        try:
            # Convert PDF to images
            logger.info(f"📸 Converting PDF to images: {pdf_path}")
            images = self.pdf_to_images(pdf_path)
            logger.info(f"✅ Converted {len(images)} pages to images")
            
            # Vision system prompt for extracting rules from image-based PDFs (German tables with ja/nein columns)
            vision_system_prompt = """You are an expert at extracting investment rules from German investment guideline tables. Your task is to achieve 100% accuracy by extracting EVERY SINGLE ROW that describes an investment instrument, asset type, or restriction.

**ACCURACY REQUIREMENTS:**
- Extract EVERY row - do not skip any, even if they seem similar
- Count rows first, then verify you extracted that exact number
- Include both main items and ALL nested sub-items
- Use EXACT instrument names as they appear in the table
- Check BOTH 'ja' and 'nein' columns carefully for each row

**CRITICAL: EXTRACT ALL ROWS SYSTEMATICALLY**
- You MUST extract EVERY row that has an 'x' mark in either the 'ja' or 'nein' column
- You MUST also extract rows with '-' marks (they indicate NOT ALLOWED)
- Do NOT skip any rows - go through the table row by row, top to bottom
- Include both main items and sub-items (nested items under categories)
- If a category has sub-items, extract each sub-item separately as its own entry
- **VERIFICATION**: Count total rows in the table and ensure you extract that exact number
- **Include every table row, even nested/sub-items, as a separate entry**

**TABLE STRUCTURE IDENTIFICATION:**
Identify these columns:
- 'nein' = no (NOT ALLOWED) - column header may be "nein", "Nicht zulässig", "Verboten", etc.
- 'ja' = yes (ALLOWED) - column header may be "ja", "Zulässig", "Erlaubt", etc.
- 'Detailrestriktionen' = detailed restrictions/conditions - may contain additional rules or limits
- Instrument name column - contains the name of the investment instrument or category

**INTERPRETATION RULES (APPLY TO EACH ROW):**
For each row, check BOTH columns carefully:
- 'x' under 'ja' column AND ('-' or empty) under 'nein' column → the item is ALLOWED (allowed = true)
- 'x' under 'nein' column AND ('-' or empty) under 'ja' column → the item is NOT ALLOWED (allowed = false)
- '-' under both columns OR both empty → typically means NOT ALLOWED (allowed = false)
- If you see 'x' in 'ja' column, that means ALLOWED - extract it with allowed=true
- If you see 'x' in 'nein' column, that means NOT ALLOWED - extract it with allowed=false
- **IMPORTANT**: Some tables may have checkboxes - an empty checkbox usually means NOT ALLOWED

**WHAT TO EXTRACT (COMPREHENSIVE LIST):**
Extract EVERY row that describes:
- Investment instruments (Aktien, Anleihen, Derivate, Options, Futures, Forwards, etc.)
- Asset types (Equities, Bonds, Derivatives, Structured Products, etc.)
- Investment categories (Staatsanleihen, Unternehmensanleihen, Pfandbriefe, Covered Bonds, etc.)
- Sub-categories (e.g., if "Anleihen" has sub-items like "Staatsanleihen", "Unternehmensanleihen", extract each separately)
- Restrictions or permissions (even if they're sub-items under main categories)
- Sector restrictions (if present in table format)
- Country restrictions (if present in table format)

**HANDLING NESTED ITEMS:**
- If a main category (e.g., "Anleihen") has sub-items listed below it (e.g., "Staatsanleihen", "Unternehmensanleihen")
- Extract the main category AND each sub-item as separate entries
- Example: If "Anleihen" has 'x' in 'ja' and has 3 sub-items, extract 4 total entries (1 main + 3 sub-items)

**VERSIONING/TRACK CHANGES (if applicable):**
- RED text/lines or strikethrough = DELETED - IGNORE completely, do NOT extract
- GREEN text/lines = NEW additions - EXTRACT these (they are current rules)
- BLACK text/lines = UNCHANGED - EXTRACT these (they are current rules)
- Only extract from BLACK and GREEN text
- If no color coding is visible, extract all rows normally

**EVIDENCE AND DETAILS:**
- Copy the EXACT instrument name as it appears in the table
- Include any text from the "Detailrestriktionen" column in the "details" field
- Include section name if visible (e.g., "A. Anlageausrichtung", "C. Anlage-Gegenstände")
- If instrument name is in German, keep it in German (do not translate)

**OUTPUT FORMAT (STRICT JSON):**
For EVERY row you find, output a JSON object with these exact fields:
{{
  "section": "<section name like 'A. Anlageausrichtung' or 'C. Anlage-Gegenstände' or 'N/A' if not visible>",
  "instrument": "<exact instrument name from the row, exactly as written (German or English)>",
  "allowed": true or false,
  "details": "<exact text from Detailrestriktionen column, or empty string if none>"
}}

**CRITICAL EXTRACTION CHECKLIST:**
Before finishing, verify:
1. Did you extract ALL rows from the table? (count them)
2. Did you include ALL nested/sub-items as separate entries?
3. Did you check BOTH 'ja' and 'nein' columns for each row?
4. Did you use the EXACT instrument names as they appear?
5. Did you extract rows with '-' marks (they indicate NOT ALLOWED)?
6. Did you skip any rows? (if yes, go back and extract them)

**OUTPUT REQUIREMENTS:**
- Output ONLY a valid JSON array - no explanations, no markdown, no additional text
- Array should contain one object for each row extracted
- Ensure JSON is valid and properly formatted
- Example format: [{{"section": "...", "instrument": "...", "allowed": true, "details": "..."}}, ...]

**REMEMBER**: Completeness is critical. If the table has 100 rows, you must extract 100 entries. Count and verify."""

            # Process each page
            all_rows = []
            max_pages = min(len(images), 20)  # Increased from 10 to 20 pages to handle longer documents
            logger.info(f"📄 Processing {max_pages} pages out of {len(images)} total pages")
            
            for page_idx, img in enumerate(images[:max_pages], start=1):
                logger.info(f"🔍 Analyzing page {page_idx}/{max_pages} with {vision_model}...")
                
                # Convert image to base64 for vision API
                img_base64 = self._image_to_base64(img)
                
                # Use standard chat.completions API for vision analysis
                api_params = {
                    "model": vision_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": """You are a document analysis expert specializing in extracting investment policy rules from German documents with tables.

CRITICAL INSTRUCTIONS:
1. Extract EVERY SINGLE ROW that has an 'x' mark in either 'ja' or 'nein' column
2. Do NOT skip any rows - be thorough and systematic
3. If 'x' is in 'ja' column, the item is ALLOWED (set allowed=true)
4. If 'x' is in 'nein' column, the item is NOT ALLOWED (set allowed=false)
5. Extract both main items and sub-items (nested items)
6. Your output must include ALL rows from the table - completeness is critical

Return ONLY a valid JSON array with all extracted rows."""
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": vision_system_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{img_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "temperature": 0
                }
                
                # Use correct parameter based on model
                # GPT-5.2 (vision_model) requires max_completion_tokens
                # Increased limit to handle documents with many rows (up to 100+ instruments)
                if vision_model in ["gpt-5", "gpt-5.1", "gpt-5.2"]:
                    api_params["max_completion_tokens"] = 8000  # Increased from 4000 to handle more rows
                elif vision_model in ["o1", "o1-mini", "o1-preview", "o1-2024-09-12", "gpt-4.1"]:
                    api_params["max_completion_tokens"] = 8000
                else:
                    api_params["max_tokens"] = 8000  # Increased from 4000 to handle more rows
                
                response = await self.client.chat.completions.create(**api_params)
                
                json_text = response.choices[0].message.content
                try:
                    cleaned = json_text.strip().strip("```json").strip("```")
                    # Clean invalid control characters before parsing
                    cleaned = _clean_json_string(cleaned)
                    page_rows = json.loads(cleaned)
                    if isinstance(page_rows, dict):
                        page_rows = [page_rows]
                    elif not isinstance(page_rows, list):
                        logger.warning(f"Unexpected JSON format on page {page_idx}, got: {type(page_rows)}")
                        page_rows = []
                    
                    # Log detailed extraction info
                    allowed_count = sum(1 for r in page_rows if r.get("allowed", False))
                    not_allowed_count = len(page_rows) - allowed_count
                    logger.info(f"✅ Page {page_idx}: Extracted {len(page_rows)} instrument rules ({allowed_count} allowed, {not_allowed_count} not allowed)")
                    
                    # Log first few extracted items for debugging
                    if page_rows:
                        logger.debug(f"📋 Sample extracted items from page {page_idx}:")
                        for i, row in enumerate(page_rows[:5], 1):
                            logger.debug(f"  {i}. {row.get('instrument', 'N/A')} - allowed={row.get('allowed', False)}")
                    
                    all_rows.extend(page_rows)
                except json.JSONDecodeError as e:
                    logger.error(f"❌ Failed to parse JSON from page {page_idx}: {e}")
                    logger.error(f"Raw response: {json_text[:500]}")
            
            # Convert rows to instrument_rules format expected by the rest of the system
            instrument_rules = []
            for row in all_rows:
                instrument_rules.append({
                    "instrument": row.get("instrument", ""),
                    "allowed": row.get("allowed", False),
                    "reason": f"Section: {row.get('section', 'N/A')}. {row.get('details', '')}"
                })
            
            # Combine results in expected format
            result = {
                "instrument_rules": instrument_rules,
                "sector_rules": [],
                "country_rules": [],
                "conflicts": []
            }
            
            # Detailed logging of extraction results
            total_allowed = sum(1 for r in instrument_rules if r.get("allowed", False))
            total_not_allowed = len(instrument_rules) - total_allowed
            logger.info(f"✅ Vision analysis complete: {len(instrument_rules)} instrument rules extracted from {len(all_rows)} rows")
            logger.info(f"📊 Extraction summary: {total_allowed} allowed, {total_not_allowed} not allowed")
            
            # Log all allowed items for debugging
            if total_allowed > 0:
                logger.info(f"✅ Allowed instruments found:")
                for rule in instrument_rules:
                    if rule.get("allowed", False):
                        logger.info(f"  - {rule.get('instrument', 'N/A')}")
            else:
                logger.warning(f"⚠️ WARNING: No allowed instruments found! This might indicate an extraction issue.")
            
            # Save to trace if available (include raw_rows for Excel mapping)
            if trace_id:
                trace_response = {
                    "provider": provider,
                    "model": vision_model,
                    "result": {
                        **result,
                        "raw_rows": all_rows  # Include raw rows for Excel mapping
                    },
                    "timestamp": time.time(),
                    "trace_id": trace_id,
                    "success": True,
                    "method": "vision",
                    "pages_processed": max_pages
                }
                await self.trace_handler.save_llm_response(trace_id, trace_response)
            
            # Validate result (without raw_rows)
            validated = self._validate_result(result)
            # Add raw_rows back after validation (for Excel mapping)
            validated["raw_rows"] = all_rows
            return validated
            
        except Exception as e:
            logger.error(f"Vision analysis error: {e}", exc_info=True)
            if trace_id:
                await self.trace_handler.save_llm_response(trace_id, {
                    "provider": provider,
                    "model": vision_model,
                    "error": str(e),
                    "timestamp": time.time(),
                    "trace_id": trace_id,
                    "success": False,
                    "method": "vision"
                })
            raise e

    def _validate_result(self, result: Dict) -> Dict:
        """Strictly validate the LLM output structure for compliance analysis"""
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM output: {result}")

        expected_keys = {"sector_rules", "country_rules", "instrument_rules", "conflicts"}
        missing = expected_keys - set(result.keys())
        if missing:
            raise ValueError(f"Missing expected keys in LLM output: {missing}")

        return result

    async def _get_llm_messages(self, provider_instance, text: str, model: str) -> List[Dict[str, str]]:
        """Extract the exact messages array that will be sent to the LLM"""
        if hasattr(provider_instance, 'api_key') and provider_instance.api_key:
            # Calculate safe text limit based on model
            # GPT-4: 8k tokens, GPT-4o/GPT-4o-mini: 128k tokens
            # Enhanced prompts are longer, so be more conservative for GPT-4
            if model == "gpt-4":
                max_text_length = 10000  # Conservative limit for GPT-4's 8k context (only truncates if text > 10k)
            elif model == "gpt-5" or model == "gpt-5.1" or model == "gpt-5.2":
                max_text_length = 500000  # GPT-5/GPT-5.1/GPT-5.2: support very large files (500k chars)
            else:
                max_text_length = 200000  # Increased limit for modern models
            
            # Truncate only if text exceeds safe limit
            text_to_analyze = text if len(text) <= max_text_length else text[:max_text_length]
            if len(text) > max_text_length:
                logger.warning(f"Document is {len(text)} chars, truncating to {max_text_length} for analysis")
            
            # Detailed system prompt for extraction (used in user role for detailed instructions)
            extraction_system_prompt = f"""You are an expert compliance analyst analyzing an official investment policy document. Your PRIMARY goal is to achieve 100% accuracy by finding ALL items that are explicitly stated as ALLOWED or PERMITTED, and ALL items that are PROHIBITED.

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

**ACCURACY FIRST - COMPLETENESS AND PRECISION:**
- Extract EVERY rule - do not miss any instrument, sector, or country mentioned
- Use EXACT quotes from the document as evidence (copy text verbatim, do not paraphrase)
- Verify completeness: count items in lists and ensure you extracted all of them
- Cross-reference sections to catch all mentions of the same rule
- If uncertain, include in conflicts rather than guessing

**CRITICAL: GERMAN DOCUMENT PATTERNS - TABLE STRUCTURE (HIGHEST PRIORITY)**
Many German investment documents use a table format with "ja" (yes) and "nein" (no) columns. This is THE PRIMARY way to identify allowed/prohibited instruments:

**TABLE FORMAT RECOGNITION:**
- Look for tables with column headers: "ja", "nein", "Detailrestriktionen", or similar
- The table structure may appear as: "Instrument Name | nein | ja | Detailrestriktionen"
- Or in text format: "Aktien | nein: - | ja: X | Detailrestriktionen: ..."
- Or as a list: "Aktien: nein: -, ja: X"
- **CRITICAL**: Even if the table structure is broken in text extraction, look for patterns like:
  * "Instrument name" followed by "ja: X" or "nein: X"
  * "Instrument name" with "X" in the "ja" column position
  * Rows where you can identify which column is "ja" and which is "nein"

**INTERPRETATION RULES FOR TABLES:**
- An "X" (cross) mark in the "ja" column = ALLOWED (allowed=true) - THIS IS THE MOST IMPORTANT RULE
- An "X" (cross) mark in the "nein" column = NOT ALLOWED (allowed=false)
- A "✓" (checkmark) in the "ja" column = ALLOWED (allowed=true)
- A "-" (hyphen/dash) in either column typically means NOT ALLOWED
- **CRITICAL**: If you see "ja: X" or "X" in the "ja" column position → that instrument is ALLOWED
- **CRITICAL**: If you see "nein: X" or "X" in the "nein" column position → that instrument is NOT ALLOWED
- **MOST IMPORTANT**: Extract EVERY row from these tables - count the rows and extract all of them

**OTHER GERMAN PATTERNS:**
- "ja" = yes/allowed, "nein" = no/not allowed
- "erlaubt", "zugelassen", "berechtigt", "darf" = allowed/permitted
- "verboten", "nicht erlaubt", "ausgeschlossen", "darf nicht" = prohibited/not allowed
- Examples in text: "FX Forwards X", "Derivatives (X)", "Options: -", "Bonds -", "Aktien ✓"

**CRITICAL: GERMAN SECTION HEADERS WITH LISTS**
When you see these German section headers, you MUST extract EVERY item in the list that follows:
- "Zulässige Anlagen" or "Zulässige Anlageinstrumente" = Permitted Investments → Extract EVERY item in the list as allowed=true
- "Unzulässige Anlagen" or "Unzulässige Anlageinstrumente" = Prohibited Investments → Extract EVERY item in the list as allowed=false
- These lists can be formatted as bullet points, numbered lists, comma-separated items, or table rows
- Each item in the list is a separate instrument that must be extracted individually
- **VERIFICATION**: Count the items in the list and ensure you extract that exact number
- Example: If you see "Zulässige Anlagen: Aktien, Bezugsrechte, Schatzanweisungen" → extract 3 separate rules:
  * {{"instrument": "Aktien", "allowed": true, "reason": "Listed in Zulässige Anlagen section: Aktien, Bezugsrechte, Schatzanweisungen"}}
  * {{"instrument": "Bezugsrechte", "allowed": true, "reason": "Listed in Zulässige Anlagen section: Aktien, Bezugsrechte, Schatzanweisungen"}}
  * {{"instrument": "Schatzanweisungen", "allowed": true, "reason": "Listed in Zulässige Anlagen section: Aktien, Bezugsrechte, Schatzanweisungen"}}

**CRITICAL: DOCUMENT VERSIONING/TRACK CHANGES (if applicable)**
Some documents use color coding to show version changes. If you detect versioning indicators:
- RED text/lines or strikethrough text = DELETED/EXCLUDED from current version - COMPLETELY IGNORE this text, do NOT extract any rules from it
- GREEN text/lines = NEW additions in current version - EXTRACT RULES FROM THIS (these are part of the current document)
- BLACK text/lines (normal text) = UNCHANGED in current version - EXTRACT RULES FROM THIS (these are part of the current document)
- If the document has versioning colors, ONLY extract rules from BLACK and GREEN text. IGNORE any RED text as it represents deleted content that is no longer valid.
- If the document does NOT have versioning colors, process all text normally using the standard extraction rules above.

**CRITICAL: You must carefully search through the ENTIRE document text provided below. Rules can appear anywhere - in the beginning, middle, end, in tables, footnotes, appendices, or any section.**

**SYSTEMATIC EXTRACTION PROCESS:**

**STEP 1: SEARCH FOR ALLOWED ITEMS FIRST (HIGHEST PRIORITY)**
Actively search for and extract EVERY item explicitly stated as:
- "allowed", "permitted", "authorized", "approved", "may invest", "can invest", "eligible"
- German: "erlaubt", "zugelassen", "berechtigt", "darf", "ja", "zulässig"
- An "X" mark in any context (tables, lists, inline text - German style)
- "FX Forwards are allowed", "currency futures are permitted", "forex is authorized"
- Lists of permitted instruments, sectors, or countries
- Any positive statement granting permission
- Phrases like: "investments are permitted in...", "the fund may invest in...", "investments in X are allowed"
- **MOST IMPORTANTLY: When you see "Zulässige Anlagen" section, extract EVERY single item in that list - verify you got them all**

**STEP 2: THEN SEARCH FOR PROHIBITED ITEMS**
Extract items explicitly stated as:
- "prohibited", "forbidden", "not allowed", "restricted", "excluded", "may not invest", "not eligible"
- German: "verboten", "nicht erlaubt", "ausgeschlossen", "darf nicht", "nein", "unzulässig"
- A "-" (hyphen) mark in any context (tables, lists, inline text - German style)
- "investments in X are not allowed", "prohibited from investing in..."
- **MOST IMPORTANTLY: When you see "Unzulässige Anlagen" section, extract EVERY single item in that list - verify you got them all**

**STEP 5: HANDLE CONDITIONAL RULES**
If a rule has conditions, extract it with allowed=true but include the condition in the reason:
- "subject to", "provided that", "up to X%", "with restrictions", "under certain conditions"
- Example: "FX Forwards allowed up to 10% of portfolio" → {{"instrument": "FX Forwards", "allowed": true, "reason": "FX Forwards allowed up to 10% of portfolio"}}
- Example: "Derivatives permitted subject to risk limits" → {{"instrument": "Derivatives", "allowed": true, "reason": "Derivatives permitted subject to risk limits"}}

**CRITICAL: DEFAULT BEHAVIOR**
- Default assumption: All instruments are NOT ALLOWED (allowed=false) unless explicitly stated as allowed/permitted
- Extract all instruments mentioned in the document
- If you find explicit evidence that an instrument is allowed (e.g., in "Zulässige Anlagen" list, or "X" mark in "ja" column), mark it as allowed=true
- If you find explicit evidence that an instrument is prohibited (e.g., in "Unzulässige Anlagen" list, or "-" mark), mark it as allowed=false
- If an instrument is mentioned but you cannot find explicit "allowed" or "prohibited" language, keep it as allowed=false (default assumption)

**STEP 6: CHECK FOR CONFLICTS**
- If the same instrument appears as both allowed and prohibited in different sections → add to conflicts
- If rules are ambiguous or contradictory → add to conflicts with explanation
- If you find unclear statements → add to conflicts rather than guessing

**INSTRUMENT NAME RECOGNITION:**
Recognize these as the SAME instrument types (but use the EXACT name from document):
- "FX Forwards" = "forex forwards" = "foreign exchange forwards" = "FX" = "forex" = "Foreign Exchange Forwards"
- "currency futures" = "FX futures" = "foreign exchange futures" = "forex futures" = "Currency Futures"
- "derivatives" includes: options, futures, forwards, swaps, warrants, structured products
- German terms: "Aktien" = stocks/shares, "Anleihen" = bonds, "Schatzanweisungen" = treasury bills, "Bezugsrechte" = subscription rights, "Pfandbriefe" = covered bonds, etc.
- **CRITICAL FOR INDEX FUTURES/OPTIONS**: Any variant of "index future" (e.g., "equity index future", "equity index futures", "Aktienindexfutures") should be treated as "index future" for rule matching. Any variant of "index option" (e.g., "equity index option", "equity index options", "Aktienindexoptionen") should be treated as "index option" for rule matching. Extract the exact name from the document, but the system will map it to the base category.
- **IMPORTANT**: Use the EXACT name as it appears in the document - do not translate unless the document itself uses both languages

**WHAT TO EXTRACT:**
- **Sectors**: Energy, Healthcare, Defense, Tobacco, Weapons, Technology, Financial Services, etc.
- **Countries**: USA, China, Russia, Europe, UK, Germany, France, etc. (use exact country names from document)
- **Instruments**: Use EXACT names from document (e.g., "FX Forwards", "currency futures", "covered bonds", "common stock", "Aktien", "Bezugsrechte", "Schatzanweisungen", etc.)
- **CRITICAL**: Extract each instrument individually - do not group them together
- **CRITICAL FOR TABLES**: Extract every table row, including nested/sub-items, as separate entries. Do not skip any rows.
- **🔴 SWAPS**: If "Swaps" is mentioned anywhere in the document, ALWAYS extract as: {{"instrument": "Swaps", "allowed": false, "reason": "Swaps are always prohibited"}} - No checking needed, always not allowed

**EVIDENCE REQUIREMENTS:**
- The "reason" field must contain the EXACT quote from the document (verbatim copy)
- Include enough context to make the rule clear
- If rule spans multiple sentences, include all relevant parts
- Minimum: include the sentence containing the rule
- Maximum: 300 characters (but prioritize completeness over length limit)

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

**COMPLETENESS VERIFICATION (MANDATORY BEFORE FINISHING):**
Before finishing, you MUST verify:
1. Did you check ALL sections of the document? (main text, tables, footnotes, appendices, introduction, investment policy, restrictions)
2. Did you extract ALL items from lists under "Zulässige Anlagen" and "Unzulässige Anlagen"?
3. Did you extract ALL rows from tables (including nested items, multi-page tables)?
4. Did you check for both allowed AND prohibited statements throughout the ENTIRE document?
5. Did you use exact quotes as evidence?
6. **CRITICAL**: Did you search systematically through the entire document, or did you only check the beginning?
7. **CRITICAL**: If this is a long document (Verkaufsprospekt/Prospectus), did you check sections that might be later in the document?
8. **CRITICAL**: Are you returning empty results? If yes, double-check - investment policy documents almost always contain rules. Search more carefully.
9. **🚨 MANDATORY FUTURES/OPTIONS VALIDATION**: For EVERY future and option you extracted:
   - Did you check for explicit prohibitions FIRST (before marking as allowed)?
   - If you marked a future/option as allowed=true, did you verify it's NOT prohibited (no "-", no "nein", not in prohibited section)?
   - Did you check the SPECIFIC "Futures" or "Options" row in tables (not just "Derivatives" row)?
   - Did you find explicit allowance evidence (not just assumed from "Derivatives" rule)?
   - If "Derivatives: X" but "Futures: -" exists, did you mark Futures as allowed=false?

**IF YOU ARE RETURNING EMPTY RESULTS:**
- STOP and re-examine the document
- Look for sections titled: "Investment Policy", "Investment Restrictions", "Zulässige Anlagen", "Unzulässige Anlagen", "Permitted Investments", "Prohibited Investments", "Investment Guidelines", "Anlagegrundsätze"
- Check tables - even if they seem unrelated, they may contain investment rules
- Look for lists of instruments, sectors, or countries
- Search for keywords: "erlaubt", "zugelassen", "verboten", "nicht erlaubt", "allowed", "permitted", "prohibited", "forbidden"
- If you still find nothing, include a conflict explaining why no rules were found

**CRITICAL RULES WITH EXAMPLES:**
1. If document says "FX Forwards are allowed" → extract: {{"instrument": "FX Forwards", "allowed": true, "reason": "FX Forwards are allowed"}}
2. If document says "currency futures are permitted" → extract: {{"instrument": "currency futures", "allowed": true, "reason": "currency futures are permitted"}}
3. If document has a section "Zulässige Anlagen" with a list of 20 items → extract 20 separate instrument rules, one for each item (verify you got all 20)
4. If document has a section "Unzulässige Anlagen" with a list of 15 items → extract 15 separate instrument rules, one for each item (verify you got all 15)
5. DO NOT mark something as "not allowed" unless explicitly prohibited - if not mentioned, do not include it
6. Search ENTIRE document systematically - rules can be in any section, table, footnote, or appendix
7. **DO NOT SKIP ITEMS IN LISTS - extract every single instrument mentioned**
8. **CRITICAL FOR TABLES: Include every table row, even nested/sub-items, as a separate entry. Extract each row individually - do not skip any rows in tables.**
9. If a table has 50 rows, extract 50 separate rules - count them to verify

**Return JSON only (no explanations, no markdown, just valid JSON):**
{{
  "sector_rules": [{{"sector": "string", "allowed": true/false, "reason": "exact quote from document"}}],
  "country_rules": [{{"country": "string", "allowed": true/false, "reason": "exact quote from document"}}],
  "instrument_rules": [{{"instrument": "string", "allowed": true/false, "reason": "exact quote from document"}}],
  "conflicts": [{{"category": "string", "detail": "string describing the conflict"}}]
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

**Document text to analyze (search through ALL of it systematically, section by section):**
{text_to_analyze}"""
            
            return [
                {
                    "role": "system",
                    "content": """You are a senior compliance analyst specializing in investment restrictions.

CRITICAL INSTRUCTIONS:
- Extract ONLY explicit rules from the provided text
- Do NOT summarize, interpret, or infer beyond what is explicitly stated
- Do NOT mix different rule categories (keep sectors, countries, instruments separate)
- Do NOT drift into general policy discussion
- Focus on specific "allowed" vs "not allowed" statements
- Look for buried restrictions in tables, footnotes, and appendices
- If text is unclear or contradictory, record it in conflicts section

Your task: Extract exact factual rules about where investments are permitted or prohibited.

Return ONLY valid JSON matching the required schema."""
                },
                {
                    "role": "user", 
                    "content": extraction_system_prompt
                }
            ]
        else:
            return [
                {
                    "role": "system",
                    "content": "You are a senior compliance analyst specializing in investment restrictions."
                },
                {
                    "role": "user",
                    "content": f"Extract explicit investment rules from this document. Search through the entire document carefully. Document text: {text[:50000] if len(text) > 50000 else text}..."
                }
            ]
