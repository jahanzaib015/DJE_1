from abc import ABC, abstractmethod

class LLMProviderInterface(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass
