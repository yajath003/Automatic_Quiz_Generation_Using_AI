import os
import requests
import json
import re
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.ai.provider import AIProvider

class GeminiProvider(AIProvider):
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API Key is missing. Set GEMINI_API_KEY environment variable.")
        
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite-001:generateContent"

    def _clean_json_response(self, text: str) -> str:
        
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```json", "", text)
            text = re.sub(r"^```", "", text)
            text = re.sub(r"```$", "", text)
        return text.strip()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, json.JSONDecodeError))
    )
    def generate_questions(
        self, 
        content: str, 
        num_questions: int, 
        difficulty: str, 
        bloom_level: str, 
        question_type: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        
        selected_topics = kwargs.get("selected_topics", [])
        teacher_note = kwargs.get("teacher_note", "")
        relax_topic = kwargs.get("relax_topic", False)
        question_styles = kwargs.get("question_styles", [])

        # Extract domain keywords from selected topics to force context-anchoring
        topic_keywords = []
        if selected_topics:
            for t in selected_topics:
                topic_keywords.extend([w for w in str(t).split() if len(w) > 3])
        keyword_hint = (
            f"\nDOMAIN KEYWORDS (must appear in questions/options): {', '.join(set(topic_keywords[:20]))}\n"
            if topic_keywords else ""
        )

        topic_instruction = ""
        if selected_topics:
            topics_str = ", ".join(str(t) for t in selected_topics)
            if relax_topic:
                topic_instruction = f"\nFocus primarily on these subtopics but stay within the resource context: {topics_str}\n"
            else:
                topic_instruction = f"\nFocus ONLY on these subtopics: {topics_str}\n"

        teacher_instruction = f"\nTeacher Constraint: {teacher_note}\n" if teacher_note else ""

        styles_instruction = ""
        if question_styles:
            styles_str = ", ".join(question_styles)
            styles_instruction = f"\nREQUIRED QUESTION STYLES FOR THIS BATCH (mix them): {styles_str}\n"

        prompt = f"""You are an expert educational assessment generator.

Generate exactly {num_questions} {question_type} questions from the content below.

Difficulty: {difficulty}
Bloom's Taxonomy Level: {bloom_level}
{topic_instruction}{teacher_instruction}{keyword_hint}{styles_instruction}

QUALITY CONSTRAINT BLOCK — Each question MUST:
- Reference specific concepts, terms, or facts directly from the input content
- Be clearly different from every other question (no structural or semantic repetition)
- Not reuse the same sentence pattern or opening phrase across questions
- Avoid all vague wording — never use: "the provided resource", "the given text", "the following content", "the above algorithm", "this method", "the given paragraph", "the process"
- Use the actual concept name instead of a pronoun or generic reference
- Vary question types: definitions, scenarios, comparisons, outputs, cause-and-effect

STRUCTURAL MIX (approximate):
- 30% Conceptual (definitions, principles)
- 30% Application (scenarios, use-cases)
- 20% Analytical (comparisons, outputs)
- 20% Direct fact recall

ADDITIONAL RULES:
- ENFORCE UNIQUE CONCEPTS: every question must test a completely different idea
- OPTIONS must be plausible, domain-specific, and semantically close to the correct answer
- All 4 options must be similar in length (within ~20 words of each other)
- Do NOT use placeholder options like "Primary aspect", "Secondary feature", "None of the above" unless genuinely appropriate
- Return ONLY valid JSON — no markdown fences, no extra text
- Output MUST start with [ and end with ]

Return format:
[
  {{
    "question": "...",
    "options": {{
        "A": "...",
        "B": "...",
        "C": "...",
        "D": "..."
    }},
    "correct_answer": "A",
    "bloom_level": "{bloom_level}",
    "difficulty": "{difficulty}"
  }}
]

Content:
\"\"\"
{content[:8000]}
\"\"\"
"""
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        try:
            response = requests.post(
                f"{self.base_url}?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
           
            if "candidates" not in result or not result["candidates"]:
                print(f"Gemini API returned no candidates: {result}")
                return []
                
            text_output = result["candidates"][0]["content"]["parts"][0]["text"]
            cleaned_text = self._clean_json_response(text_output)
            
            return json.loads(cleaned_text)
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print("Gemini API Rate Limit Hit.")
                raise e # Trigger retry
            print(f"Gemini API Error: {e}")
            raise e
        except Exception as e:
            print(f"Error generating questions: {e}")
            raise e

    def extract_topics(self, content: str) -> List[Dict[str, str]]:
        
        prompt = """
        Analyze the following text and extract main subtopics.
        Return ONLY valid JSON in this format:
        [
            {"name": "Topic Name", "content": "Summary or key points..."}
        ]
        STRICTLY JSON.
        """
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, json.JSONDecodeError))
    )
    def extract_topics(self, content: str) -> List[Dict[str, str]]:
        prompt = f"""
Analyze the following text and identify the main subtopics.

STRICT RULES:
- Return ONLY valid JSON.
- Format: [ {{"name": "Topic Name", "content": "Summary of the topic content..."}} ]
- Do NOT wrap in markdown.

Content:
\"\"\"
{content[:8000]}
\"\"\"
"""
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        try:
            response = requests.post(
                f"{self.base_url}?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            if "candidates" not in result or not result["candidates"]:
                return []
                
            text_output = result["candidates"][0]["content"]["parts"][0]["text"]
            cleaned_text = self._clean_json_response(text_output)
            return json.loads(cleaned_text)
            
        except Exception as e:
            print(f"Error extracting topics: {e}")
            return []
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException))
    )
    def generate_explanation(self, prompt: str) -> str:
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        try:
            response = requests.post(
                f"{self.base_url}?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            if "candidates" not in result or not result["candidates"]:
                return "Error: No explanation could be generated."
                
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()
            
        except Exception as e:
            print(f"Error generating explanation: {e}")
            return "Error: Failed to generate explanation."
