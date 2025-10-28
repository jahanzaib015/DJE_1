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
    """OpenAI ChatGPT provider implementation with enforced JSON output"""

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

                # Ensure it looks like JSON
                if not llm_response.startswith("{") or not llm_response.endswith("}"):
                    print("⚠️ LLM response not valid JSON, retrying with stricter instruction...")
                    return await self._retry_with_json_prompt(text, model, client, headers)

                try:
                    parsed_json = json.loads(llm_response)
                    return self._validate_and_normalize_response(parsed_json)
                except json.JSONDecodeError:
                    print("⚠️ JSON decode failed, retrying with stricter instruction...")
                    return await self._retry_with_json_prompt(text, model, client, headers)

        except Exception as e:
            raise Exception(f"OpenAI analysis failed: {str(e)}")

    async def _retry_with_json_prompt(self, text: str, model: str, client, headers) -> Dict:
        """Retry once if the model failed to return valid JSON."""
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return ONLY valid JSON matching the schema. Do not output plain text.",
                },
                {
                    "role": "user",
                    "content": f"Re-analyze this document and output valid JSON only. Document:\n{text[:2000]}",
                },
            ],
            "temperature": 0.2,
            "max_tokens": 1000,
        }

        response = await client.post(
            f"{self.base_url}/chat/completions", json=payload, headers=headers
        )
        data = response.json()
        llm_response = data["choices"][0]["message"]["content"].strip()
        print(f"🔁 Retry LLM response: {llm_response}")

        try:
            parsed_json = json.loads(llm_response)
            return self._validate_and_normalize_response(parsed_json)
        except json.JSONDecodeError:
            raise ValueError(f"LLM returned invalid JSON even after retry: {llm_response}")

    def _validate_and_normalize_response(self, parsed_json: Dict) -> Dict:
        """Validate and normalize the LLM response to ensure proper format"""
        expected_keys = ["bonds", "stocks", "funds", "derivatives"]
        normalized_response = {}

        for key in expected_keys:
            value = parsed_json.get(key, {})
            if isinstance(value, dict) and "allowed" in value:
                allowed = value["allowed"]
                evidence = value.get("evidence", "")

                if isinstance(allowed, str) and allowed.lower() in ["uncertain"]:
                    normalized_response[key] = {"allowed": "Uncertain", "evidence": evidence}
                elif allowed in [True, "true", "True"]:
                    normalized_response[key] = {"allowed": True, "evidence": evidence}
                elif allowed in [False, "false", "False"]:
                    normalized_response[key] = {"allowed": False, "evidence": evidence}
                else:
                    normalized_response[key] = {"allowed": "Uncertain", "evidence": str(allowed)}
            else:
                normalized_response[key] = {
                    "allowed": "Uncertain",
                    "evidence": "Missing or invalid format",
                }

        return normalized_response

    def get_available_models(self) -> List[str]:
        """Get available OpenAI models"""
        return ["gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
