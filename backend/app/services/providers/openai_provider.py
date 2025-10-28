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
    """OpenAI ChatGPT provider with strong JSON enforcement and fallback"""

    def __init__(self):
        self.api_key = OPENAI_API_KEY
        if not self.api_key:
            print("⚠️ Warning: OPENAI_API_KEY not configured. OpenAI provider will not be available.")
            self.api_key = None

        self.base_url = "https://api.openai.com/v1"

    async def analyze_document(self, text: str, model: str) -> Dict:
        """Analyze document using OpenAI ChatGPT"""
        if not self.api_key:
            raise Exception("OpenAI API key not configured. Please set OPENAI_API_KEY environment variable.")

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

        try:
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

                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )

                if response.status_code != 200:
                    error_data = response.json() if response.content else {}
                    raise Exception(
                        f"OpenAI API error: {response.status_code} - "
                        f"{error_data.get('error', {}).get('message', 'Unknown error')}"
                    )

                data = response.json()
                llm_response = data["choices"][0]["message"]["content"].strip()
                print(f"🔍 Raw LLM response: {llm_response}")

                # ✅ Step 1: Detect invalid responses like "bonds"
                if not llm_response.startswith("{") or not llm_response.endswith("}"):
                    print(f"⚠️ LLM returned invalid text: '{llm_response}' → applying fallback JSON")

                    return {
                        "bonds": {"allowed": "Uncertain", "evidence": f"Invalid model output: {llm_response}"},
                        "stocks": {"allowed": "Uncertain", "evidence": f"Invalid model output: {llm_response}"},
                        "funds": {"allowed": "Uncertain", "evidence": f"Invalid model output: {llm_response}"},
                        "derivatives": {"allowed": "Uncertain", "evidence": f"Invalid model output: {llm_response}"},
                    }

                # ✅ Step 2: Try to parse JSON
                try:
                    parsed_json = json.loads(llm_response)
                    return self._validate_and_normalize_response(parsed_json)
                except json.JSONDecodeError as e:
                    print(f"⚠️ JSON parse failed: {e} → applying fallback JSON")
                    return {
                        "bonds": {"allowed": "Uncertain", "evidence": f"Parsing error: {str(e)}"},
                        "stocks": {"allowed": "Uncertain", "evidence": f"Parsing error: {str(e)}"},
                        "funds": {"allowed": "Uncertain", "evidence": f"Parsing error: {str(e)}"},
                        "derivatives": {"allowed": "Uncertain", "evidence": f"Parsing error: {str(e)}"},
                    }

        except Exception as e:
            print(f"🚨 OpenAI analysis failed: {e}")
            return {
                "bonds": {"allowed": "Uncertain", "evidence": f"OpenAI error: {str(e)}"},
                "stocks": {"allowed": "Uncertain", "evidence": f"OpenAI error: {str(e)}"},
                "funds": {"allowed": "Uncertain", "evidence": f"OpenAI error: {str(e)}"},
                "derivatives": {"allowed": "Uncertain", "evidence": f"OpenAI error: {str(e)}"},
            }

    def _validate_and_normalize_response(self, parsed_json: Dict) -> Dict:
        """Validate and normalize the LLM response to ensure proper format"""
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
                    "evidence": "Missing or invalid key in model response."
                }
        return normalized

    def get_available_models(self) -> List[str]:
        """List supported OpenAI models"""
        return ["gpt-5", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]

    async def generate(self, prompt: str) -> str:
        """Legacy method for compatibility"""
        return "generate() method placeholder — not used."
