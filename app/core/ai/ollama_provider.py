import os
import requests
import json
from typing import List, Dict, Any

class OllamaProvider:

    def __init__(self, model: str = "gemma:2b"):
        self.model = model
        self.url = "http://localhost:11434/api/generate"

    def call_llm(self, prompt: str, temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """Centralized LLM service wrapper."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("OPENROUTER_MODEL", "mistralai/mixtral-8x7b-instruct")
        
        if not api_key:
            print("⚠️ OpenRouter Configuration Error: 'OPENROUTER_API_KEY' not found.")
            return "[]"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 0.95
        }
        
        for attempt in range(2):
            try:
                print(f"🚀 OpenRouter LLM Call (Attempt {attempt+1}/2) | Model: {model}")
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=45
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    choices = data.get("choices", [])
                    if not choices:
                        print("⚠️ OpenRouter Error: Valid JSON but missing 'choices'.")
                        continue
                        
                    message = choices[0].get("message", {})
                    content = message.get("content", "")
                    
                    if not content or not str(content).strip():
                        print("⚠️ OpenRouter Error: Received empty or whitespace content.")
                        continue
                        
                    return str(content)
                else:
                    print(f"⚠️ OpenRouter API Error ({response.status_code}): {response.text}")
                    
            except Exception as e:
                print(f"⚠️ OpenRouter Connection Exception (Attempt {attempt+1}/2): {str(e)}")
                
        # Safe minimal fallback to prevent downstream parser crashes
        return "[]"

    def generate_questions(self, content: str, **kwargs) -> List[Dict[str, Any]]:

        num_questions = kwargs.get("num_questions", 5)
        difficulty = kwargs.get("difficulty", "medium")
        bloom_level = kwargs.get("bloom_level", "understand")
        question_type = kwargs.get("question_type", "MCQ")
        selected_topics = kwargs.get("selected_topics", [])
        teacher_note = kwargs.get("teacher_note", "")
        relax_topic = kwargs.get("relax_topic", False)
        question_styles = kwargs.get("question_styles", [])

        # Extract domain keywords from selected topics for context-anchoring
        topic_keywords = []
        if selected_topics:
            for t in selected_topics:
                topic_keywords.extend([w for w in str(t).split() if len(w) > 3])
        keyword_hint = (
            f"\nDOMAIN KEYWORDS (must appear naturally in questions/options): {', '.join(set(topic_keywords[:20]))}\n"
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

        prompt = f"""Act as a professional educator. Based on the following content, generate EXACTLY {num_questions} {question_type} questions.

Difficulty: {difficulty}
Bloom's Taxonomy Level: {bloom_level}
{topic_instruction}{teacher_instruction}{keyword_hint}{styles_instruction}

STRUCTURAL MIX RATIO (Approximate):
- 30% Conceptual (Definitions, Principles)
- 30% Application (Scenarios, Use-cases)
- 20% Analytical (Comparisons, Outputs)
- 20% Direct Fact Recall

QUALITY CONSTRAINT BLOCK — Each question MUST:
- Reference specific concepts, terms, or facts directly from the input content
- Be clearly different from every other question (no structural or semantic repetition)
- Not reuse the same sentence pattern or opening phrase across questions
- Avoid vague wording — NEVER use: "the provided resource", "the given text", "the following content", "the above algorithm", "this method", "the given paragraph", "the process"
- Use the actual concept name instead of a pronoun or generic reference
- Vary question types: definitions, scenarios, comparisons, outputs, cause-and-effect

CRITICAL RULES:
- Each question MUST clearly state the specific concept, algorithm, or topic it is asking about.
- ENFORCE UNIQUE CONCEPTS: Every question must test a completely different idea. Do not ask similar questions.
- AVOID REPEATED PHRASING: Do not start questions with the same phrasing (e.g., skip repetitive "What is...", "How does...").
- STRICTLY FORBIDDEN Template Starters: "Which of the following...", "What is the correct answer...", "Which concept relates...".
- OPTIONS/CHOICES MUST be derived from the actual content context, plausible, semantically close to the correct answer, and similar in length to each other.
- Do NOT use placeholder options like "Primary aspect", "Secondary feature", "None of the above" unless genuinely appropriate.
- Return EXACTLY {num_questions} questions.
- Do not include explanations or extra text.
"""

        prompt += f"""
Return JSON in the following format:

[
{{
"question": "...",
"option_a": "...",
"option_b": "...",
"option_c": "...",
"option_d": "...",
"answer": "A",
"difficulty": "{difficulty}",
"bloom": "{bloom_level}"
}}
]
"""

        if kwargs.get("teacher_note"):
            prompt += f"\nSpecial Constraint: {kwargs.get('teacher_note')}\n"

        if kwargs.get("selected_topics"):
            topics_str = ", ".join(kwargs.get("selected_topics"))
            if kwargs.get("relax_topic"):
                prompt += f"\nFocus primarily on the following subtopics but stay within the context of the resource: {topics_str}\n"
            else:
                prompt += f"\nFocus ONLY on the following subtopics: {topics_str}\n"

        prompt += f"\nContent:\n{content[:3000]}\n"

        text_output = self.call_llm(prompt)
        
        if not text_output:
            print("❌ OpenRouter Error: Failed to generate questions")
            return []
        
        print(f"🔍 AI Raw Response Length: {len(text_output)}")
        
        candidates = []

        try:
            # Strategy 1: Attempt strict JSON Parse
            cleaned_text = text_output.strip()
            if "```json" in cleaned_text:
                cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned_text:
                cleaned_text = cleaned_text.split("```")[1].split("```")[0].strip()
            else:
                start = cleaned_text.find('[')
                end = cleaned_text.rfind(']')
                if start != -1 and end != -1:
                    cleaned_text = cleaned_text[start:end+1].strip()
                    
            parsed = json.loads(cleaned_text)
            if isinstance(parsed, list):
                candidates.extend(parsed)
            elif isinstance(parsed, dict):
                candidates.append(parsed)
        except json.JSONDecodeError:
            print("⚠️ Initial JSON parse failed. Engaging fallback strategies.")
            
        # Strategy 2: Contiguous standalone JSON objects
        if not candidates:
            import re
            decoder = json.JSONDecoder()
            pos = 0
            while pos < len(text_output):
                text_output_sub = text_output[pos:].lstrip()
                if not text_output_sub:
                    break
                try:
                    obj, idx = decoder.raw_decode(text_output_sub)
                    if isinstance(obj, dict):
                         candidates.append(obj)
                    elif isinstance(obj, list):
                         candidates.extend(obj)
                    pos += len(text_output[pos:]) - len(text_output_sub) + idx
                except json.JSONDecodeError:
                     next_brace = text_output_sub.find('{', 1)
                     if next_brace != -1:
                        pos += len(text_output[pos:]) - len(text_output_sub) + next_brace
                     else:
                        break

        # Strategy 3: Text Pattern Parsing (Fallback for 0 candidates)
        if not candidates:
            print("⚠️ JSON strategies failed. Initiating Regex Text Pattern Parser.")
            import re
            
            # Pattern looking for Q<num>. or <num>. followed by question text, options, and Corrent Answer.
            # This is a broad heuristic regex.
            question_blocks = re.split(r'(?m)^(?:\*\*?)?(?:Q\d+|\d+)\.?\s*', text_output)
            
            for block in question_blocks:
                if not block.strip():
                    continue
                
                lines = [line.strip() for line in block.strip().split('\n') if line.strip()]
                if len(lines) < 3:
                     continue
                     
                q_text = lines[0].replace('**', '')
                
                options = {}
                correct_ans = ""
                explanation_text = ""
                
                for line in lines[1:]:
                    line_clean = line.replace('**', '').strip()
                    # Option Match: "A) ...", "A. ...", "- A: ..."
                    opt_match = re.match(r'^(?:-\s*)?([A-D])[\)\.\:]\s*(.+)$', line_clean, re.IGNORECASE)
                    if opt_match:
                        opt_let = opt_match.group(1).upper()
                        options[opt_let] = opt_match.group(2).strip()
                        continue
                        
                    # Answer Match: "Answer: A" or "Correct Answer: A"
                    ans_match = re.match(r'^(?:Correct\s+)?Answer\s*:\s*([A-D])', line_clean, re.IGNORECASE)
                    if ans_match:
                        correct_ans = ans_match.group(1).upper()
                        continue
                        
                    # Explanation match
                    exp_match = re.match(r'^Explanation\s*:\s*(.+)$', line_clean, re.IGNORECASE)
                    if exp_match:
                        explanation_text = exp_match.group(1).strip()
                        
                if q_text and options and correct_ans:
                    candidates.append({
                        "question_text": q_text,
                        "options": options,
                        "correct_answer": correct_ans,
                        "difficulty": difficulty,
                        "explanation": explanation_text or "Explanation unavailable."
                    })

        valid_questions = []
        for q in candidates:
            if not isinstance(q, dict):
                continue
                
            # Normalize keys
            if "question" in q and "question_text" not in q:
                q["question_text"] = q.pop("question")
            
            if "answer" in q and "correct_answer" not in q:
                q["correct_answer"] = q.pop("answer")
                
            if "bloom" in q and "bloom_level" not in q:
                q["bloom_level"] = q.pop("bloom")
                
            if "options" not in q:
                q["options"] = {
                    "A": q.get("option_a", ""),
                    "B": q.get("option_b", ""),
                    "C": q.get("option_c", ""),
                    "D": q.get("option_d", "")
                }
            
            # Validation
            if "question_text" not in q or not str(q["question_text"]).strip():
                continue
            
            if "options" not in q or not isinstance(q["options"], dict):
                continue
            
            if "correct_answer" not in q:
                continue

            valid_questions.append(q)

        print(f"✅ Parsed {len(valid_questions)} questions from AI response")
        return valid_questions

    def extract_topics(self, content: str) -> List[Dict[str, str]]:

        prompt = f"""
Extract 8 to 15 clear learning subtopics from the following educational content.

Rules:
* Each topic must be short (3 to 6 words).
* Avoid numbering (e.g., '1.', '2.').
* Avoid full sentences.
* Avoid instructional text like 'Page 1'.
* Return ONLY a valid JSON list of objects with "topic_name" and "topic_content" (50-100 words summary).

Example Output:
[
  {{
    "topic_name": "Introduction to Neural Networks",
    "topic_content": "..."
  }},
  {{
    "topic_name": "Activation Functions",
    "topic_content": "..."
  }}
]

Content:
{content[:5000]}
"""

        text_output = self.call_llm(prompt)

        if not text_output:
            return []

        try:
            return json.loads(text_output)
        except:
            return []

    def generate_explanation(self, prompt: str) -> str:
        """
        Generates a text explanation for a quiz question.
        """
        try:
            text_output = self.call_llm(prompt)
            if not text_output:
                return "Explanation unavailable (AI Provider Error or Empty response)."
            return text_output.strip()
        except Exception as e:
            return f"Explanation unavailable (Connection Error: {str(e)})."
 