import requests
import json
from .provider import AIProvider


class OllamaProvider(AIProvider):

    def __init__(self, model="llama3"):
        self.model = model
        self.base_url = "http://localhost:11434/api/generate"

    def generate_questions(self, content, num_questions, difficulty, bloom_level, question_type):

        prompt = f"""
You are an educational assessment generator.

Generate {num_questions} {question_type} questions.

Difficulty: {difficulty}
Bloom Level: {bloom_level}

Return ONLY valid JSON in this format:

[
  {{
    "question_text": "...",
    "options": {{
        "A": "...",
        "B": "...",
        "C": "...",
        "D": "..."
    }},
    "correct_answer": "A"
  }}
]

Content:
{content[:3000]}
"""

        response = requests.post(
            self.base_url,
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False
            }
        )

        if response.status_code != 200:
            raise Exception(f"Ollama error: {response.text}")

        result = response.json()

        try:
            return json.loads(result["response"])
        except json.JSONDecodeError:
            raise Exception("Invalid JSON from Ollama")
    def generate_explanation(self, prompt):
        response = requests.post(
            self.base_url,
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False
            }
        )

        if response.status_code != 200:
            return "Error: Failed to generate explanation via local AI."

        result = response.json()
        return result.get("response", "").strip()
