import httpx  # pyright: ignore[reportMissingImports]
import json
import os
import sys
from typing import Dict, List
from ..llm_service import LLMProviderInterface

# Add backend directory to path to import config
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from config import OPENAI_API_KEY

class OpenAIProvider(LLMProviderInterface):
    """OpenAI ChatGPT provider implementation"""
    
    def __init__(self):
        self.api_key = OPENAI_API_KEY
        if not self.api_key:
            print("Warning: OPENAI_API_KEY not configured. OpenAI provider will not be available.")
            self.api_key = None
        
        self.base_url = "https://api.openai.com/v1"
    
    async def analyze_document(self, text: str, model: str) -> Dict:
        """Analyze document using OpenAI ChatGPT"""
        if not self.api_key:
            raise Exception("OpenAI API key not configured. Please set OPENAI_API_KEY environment variable.")
        
        # Use a prompt that requires source sentence quotes for each decision
        prompt = f"""Analyze this financial document and respond with ONLY a JSON object.

Document: {text[:2000]}

CRITICAL REQUIREMENTS:
1. For each Allowed/Disallowed decision, you MUST quote the exact source sentence(s) from the document
2. If no explicit sentence is present, return "Uncertain" for that investment type
3. Only mark as "allowed": true if you can quote specific text that explicitly permits that investment type
4. Only mark as "allowed": false if you can quote specific text that explicitly prohibits that investment type
5. If the document is ambiguous or unclear, return "Uncertain"

Respond with this exact JSON format:
{{
  "bonds": {{"allowed": true/false/Uncertain, "evidence": "exact quote from document or 'Uncertain - no explicit statement found'"}},
  "stocks": {{"allowed": true/false/Uncertain, "evidence": "exact quote from document or 'Uncertain - no explicit statement found'"}},
  "funds": {{"allowed": true/false/Uncertain, "evidence": "exact quote from document or 'Uncertain - no explicit statement found'"}},
  "derivatives": {{"allowed": true/false/Uncertain, "evidence": "exact quote from document or 'Uncertain - no explicit statement found'"}}
}}

SELF-CHECK: Before responding, verify that each decision is backed by a specific quote from the document."""
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a financial document analyst. Respond only with valid JSON. You must quote exact source sentences for each decision."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0,
                    "top_p": 1,
                    "max_tokens": 1000
                }
                
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    llm_response = data["choices"][0]["message"]["content"]
                    
                    # Parse JSON response
                    json_start = llm_response.find('{')
                    json_end = llm_response.rfind('}') + 1
                    
                    if json_start != -1 and json_end > json_start:
                        json_str = llm_response[json_start:json_end]
                        print(f"Extracted JSON string: {json_str}")  # Debug output
                        try:
                            parsed_json = json.loads(json_str)
                            print(f"Parsed JSON: {parsed_json}")  # Debug output
                            # Validate and normalize the response structure
                            normalized = self._validate_and_normalize_response(parsed_json)
                            print(f"Normalized response: {normalized}")  # Debug output
                            return normalized
                        except json.JSONDecodeError as e:
                            print(f"JSON parsing error: {e}")
                            print(f"Raw response: {llm_response}")
                            print(f"Extracted JSON: {json_str}")
                            raise ValueError(f"Invalid JSON format in OpenAI response: {e}")
                    else:
                        print(f"No JSON found in response: {llm_response}")
                        raise ValueError("No valid JSON found in OpenAI response")
                else:
                    error_data = response.json() if response.content else {}
                    raise Exception(f"OpenAI API error: {response.status_code} - {error_data.get('error', {}).get('message', 'Unknown error')}")
                    
        except Exception as e:
            raise Exception(f"OpenAI analysis failed: {str(e)}")
    
    def _validate_and_normalize_response(self, parsed_json: Dict) -> Dict:
        """Validate and normalize the LLM response to ensure proper format"""
        expected_keys = ["bonds", "stocks", "funds", "derivatives"]
        normalized_response = {}
        
        for key in expected_keys:
            if key in parsed_json:
                value = parsed_json[key]
                if isinstance(value, dict) and "allowed" in value:
                    # Handle the new format with evidence
                    allowed_value = value["allowed"]
                    evidence_value = value.get("evidence", "")
                    
                    # Normalize the allowed value
                    if allowed_value == "Uncertain" or allowed_value == "uncertain":
                        normalized_response[key] = {"allowed": "Uncertain", "evidence": evidence_value}
                    elif allowed_value in [True, "true", "True"]:
                        normalized_response[key] = {"allowed": True, "evidence": evidence_value}
                    elif allowed_value in [False, "false", "False"]:
                        normalized_response[key] = {"allowed": False, "evidence": evidence_value}
                    else:
                        # Default to uncertain if value is unclear
                        normalized_response[key] = {"allowed": "Uncertain", "evidence": f"Invalid value: {allowed_value}"}
                else:
                    # Handle old format (boolean only)
                    if value in [True, "true", "True"]:
                        normalized_response[key] = {"allowed": True, "evidence": "Legacy format - no specific evidence provided"}
                    elif value in [False, "false", "False"]:
                        normalized_response[key] = {"allowed": False, "evidence": "Legacy format - no specific evidence provided"}
                    else:
                        normalized_response[key] = {"allowed": "Uncertain", "evidence": f"Invalid value: {value}"}
            else:
                # Missing key - default to uncertain
                normalized_response[key] = {"allowed": "Uncertain", "evidence": "Key not found in response"}
        
        return normalized_response
    
    async def generate(self, prompt: str) -> str:
        """Generate text using OpenAI"""
        if not self.api_key:
            raise Exception("OpenAI API key not configured. Please set OPENAI_API_KEY environment variable.")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.7,
                    "max_tokens": 1000
                }
                
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    error_data = response.json() if response.content else {}
                    raise Exception(f"OpenAI API error: {response.status_code} - {error_data.get('error', {}).get('message', 'Unknown error')}")
                    
        except Exception as e:
            raise Exception(f"OpenAI generate failed: {str(e)}")
    
    def get_available_models(self) -> List[str]:
        """Get available OpenAI models"""
        return ["gpt-4", "gpt-3.5-turbo", "gpt-4-turbo"]
