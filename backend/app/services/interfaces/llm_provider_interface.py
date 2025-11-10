from abc import ABC, abstractmethod
from typing import Dict, List

class LLMProviderInterface(ABC):
    """Abstract interface for LLM providers"""
    
    @abstractmethod
    async def analyze_document(self, text: str, model: str) -> Dict:
        """Analyze document and extract rules"""
        pass
    
    @abstractmethod
    def get_available_models(self) -> List[str]:
        """Get list of available models for this provider"""
        pass
    
    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Legacy compatibility method"""
        pass
