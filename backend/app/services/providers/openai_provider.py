import httpx
import json
import os
import sys
from typing import Dict, List
from ..llm_service import LLMProviderInterface

# Add backend directory to path to import config
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from config import OPENAI_API_KEY


class OpenAIProvider(LLMProviderInterface):
    """OpenAI ChatGPT provider with enforced JSON output and GPT-5 fallback"""

    def __init__(self):
        self.api_key = OPENAI_API_KEY
        if not self.api_key:
            print("⚠️ Warning: OPENAI_API_KEY not configured. OpenAI provider will not be available.")
            self.api_key = None

        self.base_url = "https://api.openai.com/v1"
        # Preferred model order (highest quality first)
        self.model_priority = ["gpt-5", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]

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
                print(f"Warning: Model '{m}' failed: {e}")
                if "404" in err_msg or "does not exist" in err_msg:
                    print(f"Skipping unavailable model '{m}'...")
                    continue
                if "quota" in err_msg or "limit" in err_msg:
                    print(f"Skipping model '{m}' due to quota limit...")
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
        prompt = f"""You are analyzing an official investment policy.  
The goal is to **extract exact factual rules** about where investments are allowed or restricted.  

Work strictly with the text provided below.
Do NOT infer or guess. Do NOT include anything that is not explicitly stated.

Your task:
1. Identify every rule related to:
   - Investment sectors (e.g., Energy, Healthcare, Defense, etc.)
   - Countries or regions (e.g., USA, China, Russia, etc.)
   - Financial instruments (e.g., equities, bonds, derivatives, cash, crypto, etc.)
2. For each rule, determine:
   - Whether it is explicitly **allowed** or **not allowed**
   - A short **reason or quote** from the policy supporting your conclusion
3. If conflicting or unclear information appears, record it in a "conflicts" section.

Return only structured JSON, matching this schema exactly:
{{
  "sector_rules": [{{"sector": "string", "allowed": true/false, "reason": "string"}}],
  "country_rules": [{{"country": "string", "allowed": true/false, "reason": "string"}}],
  "instrument_rules": [{{"instrument": "string", "allowed": true/false, "reason": "string"}}],
  "conflicts": [{{"category": "string", "detail": "string"}}]
}}

Context (extract directly from this text only):
{text[:2000]}"""

        async with httpx.AsyncClient(timeout=80.0) as client:
            payload = {
                "model": model,
                "messages": [
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
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "top_p": 1,
                "max_tokens": 1000,
            }

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
            print(f"[{model}] Raw LLM response: {llm_response}")

            # Handle garbage responses like "bonds"
            if not llm_response.startswith("{") or not llm_response.endswith("}"):
                print(f"Warning: Model '{model}' returned invalid JSON — wrapping fallback.")
                return self._fallback_response(f"Invalid model output: {llm_response}")

            try:
                parsed = json.loads(llm_response)
                return self._validate_and_normalize_response(parsed)
            except json.JSONDecodeError as e:
                print(f"Warning: Model '{model}' JSON parse failed: {e}")
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
