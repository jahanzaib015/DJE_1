import httpx
import json
import os
import sys
from typing import Dict, List
from ..interfaces.llm_provider_interface import LLMProviderInterface
from ...models.llm_response_models import LLMResponse

# Add backend directory to path to import config
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from config import OPENAI_API_KEY
from ...utils.logger import setup_logger

logger = setup_logger(__name__)


class OpenAIProvider(LLMProviderInterface):
    """OpenAI ChatGPT provider with enforced JSON output and GPT-5 fallback"""

    def __init__(self):
        self.api_key = OPENAI_API_KEY
        if not self.api_key:
            logger.warning("⚠️ OPENAI_API_KEY not configured. OpenAI provider will not be available.")
            self.api_key = None

        self.base_url = "https://api.openai.com/v1"
        # Preferred model order (fastest first for speed optimization)
        # gpt-4o-mini is 2-3x faster than gpt-4o with similar quality
        self.model_priority = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]

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
                if "quota" in err_msg or "limit" in err_msg:
                    logger.warning(f"⏭️ Skipping model '{m}' due to quota limit...")
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
        # GPT-4: 8k tokens (~32k chars), GPT-4o/GPT-5: 128k tokens (~512k chars)
        # Reserve tokens for system prompt, user prompt template, and completion
        if model == "gpt-4":
            # GPT-4 has 8192 token limit: reserve ~1200 for enhanced prompts, ~2500 for completion = ~4500 tokens (~14000 chars) for document
            # Enhanced prompts are longer, so we need more conservative limits
            max_text_length = 14000  # More conservative limit to ensure we stay within 8k token context
        elif model == "gpt-4-turbo":
            # GPT-4-turbo has larger context, but be conservative
            max_text_length = 25000
        else:
            max_text_length = 100000  # Modern models - full limit for comprehensive analysis
        
        # Truncate only if text exceeds safe limit
        text_to_analyze = text if len(text) <= max_text_length else text[:max_text_length]
        if len(text) > max_text_length:
            logger.warning(f"⚠️ Document is {len(text)} chars, truncating to {max_text_length} for analysis with {model}")
        
        # Enhanced prompt that strongly emphasizes finding ALLOWED items
        prompt = f"""You are analyzing an investment policy document. Your PRIMARY goal is to find ALL items that are explicitly stated as ALLOWED or PERMITTED.

**STEP 1: SEARCH FOR ALLOWED ITEMS FIRST**
Actively search for and extract EVERY item explicitly stated as:
- "allowed", "permitted", "authorized", "approved", "may invest", "can invest"
- "FX Forwards are allowed", "currency futures are permitted", "forex is authorized"
- Lists of permitted instruments, sectors, or countries
- Any positive statement granting permission

**STEP 2: THEN SEARCH FOR PROHIBITED ITEMS**
Extract items explicitly stated as:
- "prohibited", "forbidden", "not allowed", "restricted", "excluded", "may not invest"

**INSTRUMENT NAME RECOGNITION:**
Recognize these as the SAME instrument types (use the exact name from document):
- "FX Forwards" = "forex forwards" = "foreign exchange forwards" = "FX" = "forex"
- "currency futures" = "FX futures" = "foreign exchange futures" = "forex futures"
- "derivatives" includes: options, futures, forwards, swaps, warrants

**WHAT TO EXTRACT:**
- Sectors: Energy, Healthcare, Defense, Tobacco, Weapons, Technology, etc.
- Countries: USA, China, Russia, Europe, UK, etc.
- Instruments: Use EXACT names from document (e.g., "FX Forwards", "currency futures", "covered bonds", "common stock", etc.)

**CRITICAL RULES:**
1. If document says "FX Forwards are allowed" → extract: {{"instrument": "FX Forwards", "allowed": true, "reason": "Document explicitly states FX Forwards are allowed"}}
2. If document says "currency futures are permitted" → extract: {{"instrument": "currency futures", "allowed": true, "reason": "Document explicitly states currency futures are permitted"}}
3. DO NOT mark something as "not allowed" unless explicitly prohibited
4. Search ENTIRE document - rules can be in any section, table, footnote, or appendix

**DO NOT OVER-GENERALIZE:**
- If document says "securities with equity character are allowed" → this ONLY applies to instruments explicitly described as having equity character, NOT to all bonds
- If document says "equity index options are allowed" → this ONLY applies to equity index options, NOT to all convertible bonds or structured products
- If document says "unlisted equities are allowed" → this ONLY applies to unlisted equities, NOT to debt instruments like bonds
- ONLY extract rules when the SPECIFIC instrument type is mentioned in the rule statement
- DO NOT assume a general rule applies to all similar instruments

**Return JSON only:**
{{
  "sector_rules": [{{"sector": "string", "allowed": true/false, "reason": "string"}}],
  "country_rules": [{{"country": "string", "allowed": true/false, "reason": "string"}}],
  "instrument_rules": [{{"instrument": "string", "allowed": true/false, "reason": "string"}}],
  "conflicts": [{{"category": "string", "detail": "string"}}]
}}

**Document text to analyze (search through ALL of it systematically):**
{text_to_analyze}"""

        # Use connection pooling for faster requests (reuse connections)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),  # Longer timeout for large documents, but fast connection
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        ) as client:
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a senior compliance analyst specializing in investment rules.

CRITICAL INSTRUCTIONS - READ CAREFULLY:

1. DEFAULT ASSUMPTION: If a rule is NOT explicitly stated, DO NOT mark it as "not allowed". Only mark as "not allowed" if the document EXPLICITLY prohibits or restricts it.

2. PRIORITIZE FINDING ALLOWED ITEMS: Actively search for and extract ALL items that are explicitly stated as ALLOWED, PERMITTED, or AUTHORIZED. These are just as important as prohibited items.

3. RECOGNIZE ALLOWED LANGUAGE (mark as allowed=true):
   - "permitted", "allowed", "authorized", "approved", "may invest", "can invest"
   - "investments are permitted in...", "the fund may invest in...", "investments in X are allowed"
   - "FX Forwards are allowed", "currency futures are permitted", "forex is authorized"
   - Lists of permitted instruments, sectors, or countries
   - Positive statements like "investments in [X] are permitted"

4. RECOGNIZE PROHIBITED LANGUAGE (mark as allowed=false):
   - "prohibited", "forbidden", "not allowed", "restricted", "excluded", "may not invest"
   - "investments in X are not allowed", "prohibited from investing in..."

5. INSTRUMENT NAME VARIATIONS: Recognize that these refer to the SAME instrument type:
   - "FX Forwards" = "forex forwards" = "foreign exchange forwards" = "FX" = "forex"
   - "currency futures" = "FX futures" = "foreign exchange futures" = "forex futures"
   - "derivatives" includes: options, futures, forwards, swaps, warrants
   - Extract the specific instrument name as stated in the document

6. EXTRACTION RULES:
   - Extract rules that are CLEARLY stated in the document (don't invent rules)
   - Look for buried rules in tables, footnotes, appendices - search the ENTIRE document
   - Extract rules even if stated indirectly (e.g., "prohibited from investing in tobacco" = tobacco sector not allowed)
   - Do NOT mix different rule categories (keep sectors, countries, instruments separate)
   - If text is unclear or contradictory, record it in conflicts section

7. CRITICAL: DO NOT OVER-GENERALIZE RULES
   - A rule about "securities with equity character are allowed" does NOT mean ALL bonds are allowed
   - A rule about "equity index options are allowed" does NOT mean ALL convertible bonds are allowed
   - A rule about "unlisted equities are allowed" does NOT mean ALL debt instruments are allowed
   - ONLY extract rules for instruments that are EXPLICITLY mentioned in the rule statement
   - Example: If document says "convertible bonds are allowed" → extract rule for "convertible bonds" specifically
   - Example: If document says "securities with equity character are allowed" → ONLY extract for instruments explicitly described as having equity character, NOT for regular bonds
   - DO NOT assume that a general rule applies to all similar instruments

8. CRITICAL: If the document explicitly states "FX Forwards are allowed" or "currency futures are permitted", you MUST extract this as an instrument rule with allowed=true. Do NOT miss these positive permission statements.

Your task: Systematically search through the ENTIRE document and extract ALL rules - prioritize finding what IS ALLOWED, then what is NOT ALLOWED. Extract every explicitly stated permission or prohibition.

Return ONLY valid JSON matching the required schema."""
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,  # Lower temperature for faster, more deterministic responses
                "top_p": 1,
            }
            
            # Use correct parameter name based on model
            # o1 models use max_completion_tokens, others use max_tokens
            if model in ["o1", "o1-mini", "o1-preview", "o1-2024-09-12"]:
                # Newer o1 models use max_completion_tokens
                payload["max_completion_tokens"] = 4000
            else:
                # Standard models (gpt-4o, gpt-4-turbo, etc.) use max_tokens
                # GPT-4 has 8k context window, so reduce max_tokens to fit within limit
                # Enhanced prompts are longer (~1200 tokens), so reserve ~2500 for completion
                if model == "gpt-4":
                    payload["max_tokens"] = 2500  # 8192 total - ~5500 input (enhanced prompts) - ~200 buffer
                else:
                    # Modern models (gpt-4o, gpt-4-turbo, etc.) have larger context windows
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
            llm_response = data["choices"][0]["message"]["content"].strip()
            logger.debug(f"[{model}] Raw LLM response (first 500 chars): {llm_response[:500]}")
            logger.debug(f"[{model}] Raw LLM response length: {len(llm_response)} chars")

            # Handle garbage responses like "bonds"
            if not llm_response.startswith("{") or not llm_response.endswith("}"):
                logger.warning(f"⚠️ Model '{model}' returned invalid JSON — wrapping fallback.")
                logger.debug(f"Invalid response preview: {llm_response[:200]}")
                return self._fallback_response(f"Invalid model output: {llm_response}")

            try:
                parsed = json.loads(llm_response)
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
