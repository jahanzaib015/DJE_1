import httpx
import json
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from .interfaces.llm_provider_interface import LLMProviderInterface
# from .providers.ollama_provider import OllamaProvider  # COMMENTED OUT: Only using OpenAI for now
from .providers.openai_provider import OpenAIProvider

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
    
    def get_provider(self, provider_name: str) -> LLMProviderInterface:
        """Get LLM provider by name"""
        if provider_name not in self.providers:
            raise ValueError(f"Unknown provider: {provider_name}")
        return self.providers[provider_name]
    
    async def analyze_document(self, text: str, provider: str, model: str) -> Dict:
        """Analyze document using specified provider"""
        provider_instance = self.get_provider(provider)
        return await provider_instance.analyze_document(text, model)
    
    def get_ollama_models(self) -> List[str]:
        """Get available Ollama models"""
        try:
            return self.providers["ollama"].get_available_models()
        except:
            return []
    
    def get_openai_models(self) -> List[str]:
        """Get available OpenAI models"""
        return ["gpt-4", "gpt-3.5-turbo", "gpt-4-turbo"]
