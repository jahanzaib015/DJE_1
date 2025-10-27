import httpx
import json
import os
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from .interfaces.llm_provider_interface import LLMProviderInterface
# from .providers.ollama_provider import OllamaProvider  # COMMENTED OUT: Only using OpenAI for now
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
    """Service for managing different LLM providers"""
    
    def __init__(self):
        self.providers = {
            # "ollama": OllamaProvider(),  # COMMENTED OUT: Only using OpenAI for now
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
        
        try:
            # Try requested model first
            return await provider_instance.analyze_document(text, model)
        except Exception as e:
            # Fallback if model not available or returns a 404
            if "404" in str(e) or "does not exist" in str(e):
                print(f"[Warning] Model '{model}' unavailable. Falling back to 'gpt-4o-mini'")
                return await provider_instance.analyze_document(text, "gpt-4o-mini")
            raise e
    
    async def analyze_document_with_tracing(self, text: str, provider: str, model: str, trace_id: str) -> Dict:
        """Analyze document with forensic tracing"""
        provider_instance = self.get_provider(provider)
        
        # Create prompt data for tracing
        prompt_data = {
            "provider": provider,
            "model": model,
            "text_length": len(text),
            "text_preview": text[:500] + "..." if len(text) > 500 else text,
            "timestamp": time.time(),
            "trace_id": trace_id
        }
        
        # Save prompt data
        await self.trace_handler.save_llm_prompt(trace_id, prompt_data)
        
        try:
            # Get analysis result
            result = await provider_instance.analyze_document(text, model)
            
            # Create response data for tracing
            response_data = {
                "provider": provider,
                "model": model,
                "result": result,
                "timestamp": time.time(),
                "trace_id": trace_id,
                "success": True
            }
            
            # Save response data
            await self.trace_handler.save_llm_response(trace_id, response_data)
            
            return result
            
        except Exception as e:
            # Create error response data for tracing
            error_data = {
                "provider": provider,
                "model": model,
                "error": str(e),
                "timestamp": time.time(),
                "trace_id": trace_id,
                "success": False
            }
            
            # Save error response
            await self.trace_handler.save_llm_response(trace_id, error_data)
            
            raise e
    
    def get_ollama_models(self) -> List[str]:
        """Get available Ollama models"""
        try:
            return self.providers["ollama"].get_available_models()
        except Exception:
            return []
    
    def get_openai_models(self) -> List[str]:
        """Get available OpenAI models"""
        # Updated list — includes the ones your API key supports
        return ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
