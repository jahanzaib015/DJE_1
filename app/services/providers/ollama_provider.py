import httpx
import json
from typing import Dict, List
from ..interfaces.llm_provider_interface import LLMProviderInterface

class OllamaProvider(LLMProviderInterface):
    """Ollama LLM provider implementation"""
    
    def __init__(self, host: str = "localhost", port: int = 11434):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"

    async def generate(self, prompt: str) -> str:
        """Implements required abstract method for LLMProviderInterface"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "model": "llama3.1",   # or any default model
                    "prompt": prompt,
                    "stream": False,
                }
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
        except Exception as e:
            raise Exception(f"Ollama generate() failed: {str(e)}")

    async def analyze_document(self, text: str, model: str) -> Dict:
        """Analyze document using Ollama"""
        prompt = f"""Analyze this financial document and respond with ONLY a JSON object.

Document: {text[:2000]}

Respond with this exact JSON format:
{{"bonds": true/false, "stocks": true/false, "funds": true/false, "derivatives": true/false}}

Only mark as true if the document explicitly allows that type of investment."""
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "top_p": 0.9}
                }
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                data = response.json()
                llm_response = data.get("response", "")
                
                # Extract and parse JSON block
                json_start = llm_response.find('{')
                json_end = llm_response.rfind('}') + 1
                if json_start != -1 and json_end > json_start:
                    json_str = llm_response[json_start:json_end]
                    return json.loads(json_str)
                else:
                    raise ValueError("No valid JSON found in Ollama response")
                    
        except Exception as e:
            raise Exception(f"Ollama analysis failed: {str(e)}")
    
    def get_available_models(self) -> List[str]:
        """Get available Ollama models"""
        try:
            import requests
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [model["name"] for model in data.get("models", [])]
            return []
        except:
            return []
