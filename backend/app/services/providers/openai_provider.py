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
        # Reserve ~4k tokens for prompt and response
        if model in ["gpt-4", "gpt-4-turbo"]:
            max_text_length = 25000  # ~6k tokens for GPT-4 (8k context - 2k for prompt/response)
        else:
            max_text_length = 100000  # Modern models - full limit for comprehensive analysis
        
        # Truncate only if text exceeds safe limit
        text_to_analyze = text if len(text) <= max_text_length else text[:max_text_length]
        if len(text) > max_text_length:
            logger.warning(f"⚠️ Document is {len(text)} chars, truncating to {max_text_length} for analysis with {model}")
        
        # Optimized prompt that explicitly looks for BOTH allowed and restricted items
        prompt = f"""Extract investment rules from this document. Search entire text.

CRITICAL: Look for BOTH:
- What IS ALLOWED: "permitted", "allowed", "authorized", "may invest", "can invest"
- What IS NOT ALLOWED: "prohibited", "forbidden", "not allowed", "restricted", "excluded"

Rules to find:
- Sectors: Energy, Healthcare, Defense, Tobacco, Weapons, etc.
- Countries: USA, China, Russia, Europe, etc.  
- Instruments: bonds, stocks, funds, derivatives, options, futures, swaps, etc.

IMPORTANT: If document says investments are generally permitted, mark instruments as allowed=true. Only mark as not allowed if explicitly prohibited.

For each rule found, mark "allowed": true if permitted, false if prohibited, with brief reason.

Return JSON only:
{{
  "sector_rules": [{{"sector": "string", "allowed": true/false, "reason": "string"}}],
  "country_rules": [{{"country": "string", "allowed": true/false, "reason": "string"}}],
  "instrument_rules": [{{"instrument": "string", "allowed": true/false, "reason": "string"}}],
  "conflicts": [{{"category": "string", "detail": "string"}}]
}}

Document:
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
                        "content": """You are a senior compliance analyst specializing in investment restrictions.

CRITICAL INSTRUCTIONS:
- Extract rules that are CLEARLY stated in the document (don't invent rules that aren't there)
- Look for BOTH allowed AND prohibited items - don't only focus on restrictions
- Recognize common policy language: "permitted", "allowed", "authorized", "may invest", "can invest" = allowed=true; "prohibited", "forbidden", "not allowed", "restricted", "excluded", "may not invest" = allowed=false
- IMPORTANT: If document says investments are generally permitted or lists what can be invested in, mark those as allowed=true
- Only mark as not allowed if explicitly prohibited or restricted
- Extract rules even if they're stated indirectly (e.g., "prohibited from investing in tobacco" = tobacco sector not allowed)
- Do NOT mix different rule categories (keep sectors, countries, instruments separate)
- Look for buried rules in tables, footnotes, and appendices - search the ENTIRE document
- If text is unclear or contradictory, record it in conflicts section

Your task: Extract factual rules about where investments are permitted OR prohibited. Search through the entire document systematically and extract ALL rules you can identify - both what IS allowed and what is NOT allowed.

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
                # Keep full max_tokens for comprehensive rule extraction
                payload["max_tokens"] = 4000

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
