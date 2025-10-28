import httpx
import json
import os
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from .interfaces.llm_provider_interface import LLMProviderInterface
from .providers.openai_provider import OpenAIProvider
from ..utils.trace_handler import TraceHandler


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
        self.providers = {
            "openai": OpenAIProvider()
        }
        self.trace_handler = TraceHandler()
    
    def get_provider(self, provider_name: str) -> LLMProviderInterface:
        """Get LLM provider by name"""
        if provider_name not in self.providers:
            raise ValueError(f"Unknown provider: {provider_name}")
        return self.providers[provider_name]
    
    async def analyze_document(self, text: str, provider: str, model: str, trace_id: Optional[str] = None) -> Dict:
        """Analyze document using specified provider with automatic fallback"""
        provider_instance = self.get_provider(provider)

        if trace_id:
            messages = await self._get_llm_messages(provider_instance, text, model)
            prompt_data = {
                "model": model,
                "temperature": 0,
                "top_p": 1,
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
            return self._validate_result(result)
        except Exception as e:
            err_msg = str(e).lower()

            # Handle model not available
            if "404" in err_msg or "does not exist" in err_msg:
                print(f"[Warning] Model '{model}' unavailable. Falling back to 'gpt-4o-mini'")
                try:
                    result = await provider_instance.analyze_document(text, "gpt-4o-mini")
                    return self._validate_result(result)
                except Exception as inner_e:
                    print(f"[Warning] gpt-4o-mini also failed, falling back to 'gpt-3.5-turbo'")
                    result = await provider_instance.analyze_document(text, "gpt-3.5-turbo")
                    return self._validate_result(result)
            
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
        """Strictly validate the LLM output structure"""
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM output: {result}")

        expected_keys = {"bonds", "stocks", "funds", "derivatives"}
        missing = expected_keys - set(result.keys())
        if missing:
            raise ValueError(f"Missing expected keys in LLM output: {missing}")

        return result

    async def _get_llm_messages(self, provider_instance, text: str, model: str) -> List[Dict[str, str]]:
        """Extract the exact messages array that will be sent to the LLM"""
        if hasattr(provider_instance, 'api_key') and provider_instance.api_key:
            prompt = f"""Analyze this financial document and respond with ONLY a JSON object.

Document: {text[:2000]}

For each investment type that is explicitly allowed, provide the specific text from the document that supports this conclusion.

Respond with this exact JSON format:
{{
  "bonds": {{"allowed": true/false, "evidence": "specific quote from document or empty string"}},
  "stocks": {{"allowed": true/false, "evidence": "specific quote from document or empty string"}},
  "funds": {{"allowed": true/false, "evidence": "specific quote from document or empty string"}},
  "derivatives": {{"allowed": true/false, "evidence": "specific quote from document or empty string"}}
}}

Only mark as true if the document explicitly allows that type of investment. For evidence, provide the exact text from the document that mentions this permission."""
            
            return [
                {
                    "role": "system",
                    "content": "You are a financial document analyst. Respond only with valid JSON."
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
                    "content": "You are a financial document analyst."
                },
                {
                    "role": "user",
                    "content": f"Analyze this document: {text[:1000]}..."
                }
            ]
