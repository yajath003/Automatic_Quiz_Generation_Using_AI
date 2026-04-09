from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class AIProvider(ABC):
    """
    Abstract Base Class for AI Providers.
    Ensures that any AI service (Gemini, OpenAI, etc.) adheres to this contract.
    """

    @abstractmethod
    def generate_questions(
        self, 
        content: str, 
        num_questions: int, 
        difficulty: str, 
        bloom_level: str, 
        question_type: str
    ) -> List[Dict[str, Any]]:
        """
        Generates questions from the given content.

        :param content: The text content to generate questions from.
        :param num_questions: Number of questions to generate.
        :param difficulty: Difficulty level (e.g., 'medium').
        :param bloom_level: Bloom's Taxonomy level (e.g., 'apply').
        :param question_type: Type of questions (e.g., 'MCQ', 'MSQ').
        :return: A list of dictionaries representing the questions.
        """
        pass

    @abstractmethod
    def extract_topics(self, content: str) -> List[Dict[str, str]]:
        """
        Extracts subtopics from the given content.

        :param content: The text content to analyze.
        :return: A list of topics with 'name' and 'content' keys.
        """
        pass

    @abstractmethod
    def generate_explanation(self, prompt: str) -> str:
        """
        Generates a plain text explanation based on the given prompt.

        :param prompt: The instruction for the AI.
        :return: A plain text explanation.
        """
        pass
