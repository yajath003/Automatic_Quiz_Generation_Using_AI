from app.core.ai.factory import AIFactory
from typing import List, Dict, Any

class AIService:
    def __init__(self):
        self.provider = AIFactory.get_provider()

    def generate_questions(self, content: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Orchestrates question generation.
        """
        if not content or len(content.strip()) < 50:
            return []
            
        return self.provider.generate_questions(content, **kwargs)

    def extract_topics(self, content: str) -> List[Dict[str, str]]:
        """
        Orchestrates topic extraction.
        """
        if not content:
            return []
            
        return self.provider.extract_topics(content)
    def generate_explanation(self, prompt: str) -> str:
        """
        Orchestrates explanation generation.
        """
        return self.provider.generate_explanation(prompt)
