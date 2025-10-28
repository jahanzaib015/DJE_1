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
                print(f"⚠️ Model '{m}' failed: {e}")
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
            "bonds": {"allowed": "Uncertain", "evidence": f"All models failed: {tried_models}"},
            "stocks": {"allowed": "Uncertain", "evidence": f"All models failed: {tried_models}"},
            "funds": {"allowed": "Uncertain", "evidence": f"All models failed: {tried_models}"},
            "derivatives": {"allowed": "Uncertain", "evidence": f"All models failed: {tried_models}"}
        }

    async def _analyze_with_model(self, text: str, model: str) -> Dict:
        """Core analysis call to OpenAI API"""
        prompt = f"""
You are a financial compliance analyst. Analyze the following document
and determine if each investment category is explicitly allowed or prohibited.

Respond **ONLY** with valid JSON. Do not include explanations, notes, or commentary.

Document (first 2000 chars shown):
{text[:2000]}

Return JSON in this format exactly:
{{
  "bonds": {{
    "allowed": true/false/"Uncertain",
    "evidence": "exact quoted sentence or 'Uncertain - not found'"
  }},
  "stocks": {{
    "allowed": true/false/"Uncertain",
    "evidence": "exact quoted sentence or 'Uncertain - not found'"
  }},
  "funds": {{
    "allowed": true/false/"Uncertain",
    "evidence": "exact quoted sentence or 'Uncertain - not found'"
  }},
  "derivatives": {{
    "allowed": true/false/"Uncertain",
    "evidence": "exact quoted sentence or 'Uncertain - not found'"
  }}
}}

If you cannot find explicit mentions, mark as "Uncertain".
If unsure, still return valid JSON — never output plain text.
"""

        async with httpx.AsyncClient(timeout=80.0) as client:
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a precise financial document parser. Always respond in valid JSON only."
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
            print(f"🧠 [{model}] Raw LLM response: {llm_response}")

            # Handle garbage responses like "bonds"
            if not llm_response.startswith("{") or not llm_response.endswith("}"):
                print(f"⚠️ Model '{model}' returned invalid JSON — wrapping fallback.")
                return self._fallback_response(f"Invalid model output: {llm_response}")

            try:
                parsed = json.loads(llm_response)
                return self._validate_and_normalize_response(parsed)
            except json.JSONDecodeError as e:
                print(f"⚠️ Model '{model}' JSON parse failed: {e}")
                return self._fallback_response(f"Parsing error from {model}: {str(e)}")

    def _fallback_response(self, reason: str) -> Dict:
        """Return safe fallback JSON"""
        return {
            "bonds": {"allowed": "Uncertain", "evidence": reason},
            "stocks": {"allowed": "Uncertain", "evidence": reason},
            "funds": {"allowed": "Uncertain", "evidence": reason},
            "derivatives": {"allowed": "Uncertain", "evidence": reason}
        }

    def _validate_and_normalize_response(self, parsed_json: Dict) -> Dict:
        """Ensure consistent structure"""
        expected_keys = ["bonds", "stocks", "funds", "derivatives"]
        normalized = {}
        for key in expected_keys:
            value = parsed_json.get(key, {})
            if isinstance(value, dict) and "allowed" in value:
                normalized[key] = {
                    "allowed": value.get("allowed", "Uncertain"),
                    "evidence": value.get("evidence", "No explicit evidence found.")
                }
            else:
                normalized[key] = {
                    "allowed": "Uncertain",
                    "evidence": "Missing or invalid structure."
                }
        return normalized

    def get_available_models(self) -> List[str]:
        """List supported OpenAI models"""
        return self.model_priority

    async def generate(self, prompt: str) -> str:
        """Legacy compatibility"""
        return "generate() method placeholder — not used."
