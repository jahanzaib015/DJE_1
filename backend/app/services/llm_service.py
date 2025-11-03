import httpx
import json
import os
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from openai import AsyncOpenAI
import openai
from .interfaces.llm_provider_interface import LLMProviderInterface
from .providers.openai_provider import OpenAIProvider
from ..utils.trace_handler import TraceHandler

# Robust system prompt for compliance analysis
SYSTEM_PROMPT = """You are a senior compliance analyst specializing in investment restrictions.

CRITICAL INSTRUCTIONS:
- Extract ONLY explicit rules from the provided text
- Do NOT summarize, interpret, or infer beyond what is explicitly stated
- Do NOT mix different rule categories (keep sectors, countries, instruments separate)
- Do NOT drift into general policy discussion
- Focus on specific "allowed" vs "not allowed" statements
- Look for buried restrictions in tables, footnotes, and appendices
- If text is unclear or contradictory, record it in conflicts section

Your task: Extract exact factual rules about where investments are permitted or prohibited.

Return ONLY valid JSON matching the required schema:
{
  "sector_rules": [
    {"sector": "string", "allowed": true/false, "reason": "string"}
  ],
  "country_rules": [
    {"country": "string", "allowed": true/false, "reason": "string"}
  ],
  "instrument_rules": [
    {"instrument": "string", "allowed": true/false, "reason": "string"}
  ],
  "conflicts": [
    {"category": "string", "detail": "string"}
  ]
}"""


class LLMProviderInterface(ABC):
    """Abstract interface for LLM providers"""
    
    @abstractmethod
    async def analyze_document(self, text: str, model: str) -> Dict:
        pass
    
    @abstractmethod
    def get_available_models(self) -> List[str]:
        pass


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
                http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(60.0),
                    # Explicitly don't pass proxies parameter
                )
                
                # Initialize AsyncOpenAI client with custom http_client
                self.client = AsyncOpenAI(
                    api_key=api_key,
                    http_client=http_client
                )
            except Exception as e:
                print(f"Warning: Failed to initialize OpenAI client: {str(e)}")
                print("Warning: OpenAI API key not found. Embedding generation will be disabled.")
                self.client = None
        else:
            print("Warning: OpenAI API key not found. Embedding generation will be disabled.")
        
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
            return json.loads(cleaned)

        except Exception as e:
            print("LLM Error:", e)
            return {"error": str(e)}
    
    async def analyze_document(self, text: str, provider: str, model: str, trace_id: Optional[str] = None) -> Dict:
        """Analyze document using new OpenAI client with robust system prompt"""
        if not self.client:
            raise ValueError("OpenAI client not initialized. Please set OPENAI_API_KEY environment variable.")
        
        # Create dynamic user prompt
        user_prompt = f"""You are analyzing an official investment policy.  
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
                "user_prompt": user_prompt
            }
            await self.trace_handler.save_llm_prompt(trace_id, prompt_data)

        try:
            # Use new OpenAI client approach
            response = await self.client.chat.completions.create(
                model=model,
                temperature=0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]
            )
            raw = response.choices[0].message.content

            # Parse JSON safely
            cleaned = raw.strip().strip("```json").strip("```")
            result = json.loads(cleaned)
            
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
                print(f"Warning: Model '{model}' unavailable. Falling back to 'gpt-4o-mini'")
                try:
                    response = await self.client.chat.completions.create(
                        model="gpt-4o-mini",
                        temperature=0,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt}
                        ]
                    )
                    raw = response.choices[0].message.content
                    cleaned = raw.strip().strip("```json").strip("```")
                    result = json.loads(cleaned)
                    return self._validate_result(result)
                except Exception as inner_e:
                    print(f"Warning: gpt-4o-mini also failed, falling back to 'gpt-3.5-turbo'")
                    response = await self.client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        temperature=0,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt}
                        ]
                    )
                    raw = response.choices[0].message.content
                    cleaned = raw.strip().strip("```json").strip("```")
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
        return ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]

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
                    "content": prompt
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
                    "content": f"Extract explicit investment rules from this document: {text[:1000]}..."
                }
            ]
