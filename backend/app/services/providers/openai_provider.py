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
        
        # Use a simplified prompt for faster processing
        prompt = f"""Analyze this financial document and respond with ONLY a JSON object.

Document: {text[:2000]}

Respond with this exact JSON format:
{{"bonds": true/false, "stocks": true/false, "funds": true/false, "derivatives": true/false}}

Only mark as true if the document explicitly allows that type of investment."""
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a financial document analyst. Respond only with valid JSON."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500
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
                        return json.loads(json_str)
                    else:
                        raise ValueError("No valid JSON found in OpenAI response")
                else:
                    error_data = response.json() if response.content else {}
                    raise Exception(f"OpenAI API error: {response.status_code} - {error_data.get('error', {}).get('message', 'Unknown error')}")
                    
        except Exception as e:
            raise Exception(f"OpenAI analysis failed: {str(e)}")
    
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
