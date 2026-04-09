import os
import requests
import json
import re
import logging

logger = logging.getLogger(__name__)

def clean_json_response(text):
    text = text.strip()
    
    if "```" in text:
        text = re.sub(r"```json", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```", "", text)
    
    # Extract the main JSON list using Regex
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        text = match.group(0)
        
    return text.strip()

def get_prompt_template(question_type, num_questions, difficulty, bloom_level, content, teacher_note=None):
    
    base_instructions = f"""
Act as a professional educator. Based on the following text, generate a quiz with exactly 5 {question_type} questions.

Structure:
- 2 Easy questions (Basic recall of facts)
- 2 Medium questions (Application of concepts)
- 1 Hard question (Analysis or evaluation)

Bloom Level focus: {bloom_level}

STRICT OUTPUT RULES:
1. You MUST return EXACTLY {num_questions} questions.
2. Before responding, count the number of generated questions. If it is not exactly {num_questions}, regenerate internally.
3. Return ONLY a single valid JSON array.
4. Each object in the array must contain: "question", "options", "correct_answer", "difficulty", and "explanation".
5. If you cannot generate the exact number, regenerate until you can.
6. No extra conversational text before or after the JSON array.
7. No markdown formatting (No ```json or ``` blocks).
8. No trailing commas in JSON.
9. No extra text before or after the JSON array.
10. Ensure the array length equals {num_questions} exactly.
"""

    if question_type == "MCQ":
        format_instructions = """
JSON Format:
[
  {
    "question": "Question text here...",
    "options": {
      "A": "Option A text",
      "B": "Option B text",
      "C": "Option C text",
      "D": "Option D text"
    },
    "correct_answer": "A"  
  }
]
"""
    elif question_type == "MSQ":
        format_instructions = """
JSON Format:
[
  {
    "question": "Question text here (Select all that apply)...",
    "options": {
      "A": "Option A text",
      "B": "Option B text",
      "C": "Option C text",
      "D": "Option D text"
    },
    "correct_answer": ["A", "C"]  
  }
]
"""
    elif question_type == "NAT":
        format_instructions = """
JSON Format:
[
  {
    "question": "Question text here...",
    "options": {},
    "correct_answer": 42.5 
  }
]
Note: For NAT, provide an empty object for "options" to maintain structural consistency.
"""
    else:  
        format_instructions = """
JSON Format:
[
  {
    "question": "Question text here...",
    "options": {"A": "...", "B": "..." , "C": "...", "D": "..."},
    "correct_answer": "A",
    "difficulty": "Easy/Medium/Hard",
    "explanation": "..."
  }
]
"""

    if teacher_note:
        final_prompt = f"""
{base_instructions}

{format_instructions}

Special Constraint:
{teacher_note}

Content:
\"\"\"
{content[:8000]} 
\"\"\"
"""
    else:
        final_prompt = f"""
{base_instructions}

{format_instructions}

Content:
\"\"\"
{content[:8000]} 
\"\"\"
"""
    return final_prompt

def validate_questions(questions, question_type):
    
    valid_questions = []
    
    for q in questions:
        try:
            if "question" not in q:
                continue
                
            if question_type == "NAT":
                if "options" in q and q["options"]:
                    logger.warning(f"Skipping NAT question with options: {q}")
                    continue
                if "correct_answer" not in q:
                    continue
                    
            elif question_type in ["MCQ", "MSQ"]:
                if "options" not in q or not isinstance(q["options"], dict) or not q["options"]:
                    logger.warning(f"Skipping {question_type} question without valid options: {q}")
                    continue
                if question_type == "MCQ":
                    if not isinstance(q.get("correct_answer"), str):
                        logger.warning(f"Skipping MCQ with non-string answer: {q}")
                        continue
                elif question_type == "MSQ":
                    if not isinstance(q.get("correct_answer"), list):
                        logger.warning(f"Skipping MSQ with non-list answer: {q}")
                        continue
            
            valid_questions.append(q)
            
        except Exception as e:
            logger.error(f"Validation error for question {q}: {e}")
            continue
            
    return valid_questions

def generate_questions_from_text(content, num_questions, difficulty, bloom_level, question_type, teacher_note=None):

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        logger.error("GEMINI_API_KEY not found in environment variables")
        return []

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite-001:generateContent?key={api_key}"

    prompt = get_prompt_template(question_type, num_questions, difficulty, bloom_level, content, teacher_note)

    headers = {
        "Content-Type": "application/json"
    }

    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status() 
    except requests.exceptions.RequestException as e:
        logger.error(f"Gemini API Request Failed: {e}")
        return []

    result = response.json()

    try:
        if "candidates" not in result or not result["candidates"]:
            logger.error("No candidates returned from Gemini.")
            return []
            
        text_output = result["candidates"][0]["content"]["parts"][0]["text"]

        cleaned_text = clean_json_response(text_output)
        
        try:
            parsed_json = json.loads(cleaned_text)
        except json.JSONDecodeError:
            logger.warning("Initial JSON parse failed. Raw text: " + cleaned_text[:100])
            return []

        if not isinstance(parsed_json, list):
            logger.warning("AI response was not a list.")
            return []
         
        valid_questions = validate_questions(parsed_json, question_type)
        
        if len(valid_questions) < len(parsed_json):
            logger.warning(f"Filtered out {len(parsed_json) - len(valid_questions)} invalid questions.")

        return valid_questions

    except Exception as e:
        logger.error(f"Parsing Error: {e}")
        logger.debug(f"Raw Output: {result}")
        return []
