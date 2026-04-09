from typing import List, Dict
from app import db
from app.models import (
    Quiz,
    QuizAttempt,
    Resource,
    ResourceTopic,
    GeneratedQuestion,
    AttemptAnswer,
    Assignment,
    AssignmentAttempt,
    AssignmentUser
)
from app.services.ai_service import AIService
import itertools
import json
import logging
from sentence_transformers import SentenceTransformer, util

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Lazy load model to save memory/speed if not always needed, or load once globally
# We'll load it once globally for the worker to reuse
try:
    similarity_model = SentenceTransformer('all-MiniLM-L6-v2')
except Exception as e:
    logger.error(f"Failed to load sentence-transformers model: {e}")
    similarity_model = None
logger = logging.getLogger(__name__)


class QuizService:
    def __init__(self):
        self.ai_service = AIService()

    def get_topics(self, resource_id: int) -> List[ResourceTopic]:
        """
        Retrieves all topics for a resource.
        """
        return ResourceTopic.query.filter_by(resource_id=resource_id).all()

    def _clean_topic_name(self, name: str) -> str:
        """
        Cleans topic names by removing numeric prefixes, procedural words,
        and excessively short/meaningless phrases.
        """
        import re
        
        # 1. Strip leading numbers, bullets, dots, or dashes (e.g., "1. ", "(1)", "- ")
        clean_name = re.sub(r'^[\d\s\.\(\)\-]+(?=[a-zA-Z])', '', name)
        
        # 2. Strip procedural prefixes like "Step 1:", "Chapter 2:", "Section A."
        clean_name = re.sub(r'^(step|chapter|section|part)\s*[\da-zA-Z]*[\:\.\-]?\s*', '', clean_name, flags=re.IGNORECASE)
        
        # 3. Strip extremely generic procedural words if they lead or trail
        clean_name = re.sub(r'^(input|output|print|display|calculate|compute)\b\s*', '', clean_name, flags=re.IGNORECASE)
        
        # Finally, strip whitespace
        clean_name = clean_name.strip()
        
        # If the resulting name is too short (e.g., < 3 chars) or empty, return original (or empty to drop it)
        if len(clean_name) < 3:
            return ""
            
        return clean_name

    def process_resource_topics(self, resource_id: int):
        """
        Extracts subtopics using AI and saves them to DB.
        Follows a Level 1 (AI) -> Level 2 (Text-Based) fallback chain.
        """
        resource = Resource.query.get(resource_id)
        if not resource or not resource.content:
            return

        topics_data = []
        try:
            # Level 1: AI Extraction
            logger.info(f"Level 1: Running AI Topic Extraction for resource {resource_id}.")
            topics_data = self.ai_service.extract_topics(resource.content)
            
            if isinstance(topics_data, dict):
                topics_data = [topics_data]
            elif not isinstance(topics_data, list):
                topics_data = []
                
        except Exception as e:
            logger.error(f"AI Topic Extraction Exception: {e}")
            topics_data = []

        # Filter and clean AI topics
        valid_topics = []
        for t in topics_data:
            if isinstance(t, dict) and 'topic_name' in t:
                name = self._clean_topic_name(t.get('topic_name', ''))
                # Clean short phrases (< 2 words)
                if name and len(name.split()) >= 2:
                    valid_topics.append({"topic_name": name, "topic_content": t.get('topic_content', '')})

        # Level 2 — Text-Based Extraction (Trigger if AI returned < 5)
        if len(valid_topics) < 5:
            logger.info(f"Level 1 (AI) returned only {len(valid_topics)} topics. Level 2 fallback triggering.")
            fallback = self._fallback_topic_extraction(resource.content)
            
            existing_names = {t['topic_name'].lower() for t in valid_topics}
            for f_topic in fallback:
                 name = self._clean_topic_name(f_topic['topic_name'])
                 if name and name.lower() not in existing_names and len(name.split()) >= 2:
                     valid_topics.append({"topic_name": name, "topic_content": f_topic['topic_content']})
                     existing_names.add(name.lower())

        # Deduplicate
        seen = set()
        final_topics = []
        for t in valid_topics:
            n_lower = t['topic_name'].lower()
            if n_lower not in seen:
                seen.add(n_lower)
                final_topics.append(t)

        try:
            # Drop old topics to prevent duplicates if fixing a broken state
            # Wait, Part 10 says Do Not Modify Flow. Subtopics insertion normally happens once.
            for t_data in itertools.islice(final_topics, 15): # Cap at 15
                topic = ResourceTopic(
                    resource_id=resource.id,
                    topic_name=t_data['topic_name'],
                    topic_content=t_data.get('topic_content', 'Subtopic extracted from resource.')
                )
                db.session.add(topic)
                
            db.session.commit()
            logger.info(f"Stored {len(final_topics)} topics for resource {resource_id}")
        except Exception as e:
            logger.error(f"Failed to commit topics into DB: {e}")
            db.session.rollback()

    def _fallback_topic_extraction(self, content: str) -> List[Dict[str, str]]:
        """
        Level 2 NLP fallback to extract potential subtopics from text using headings and lists.
        """
        import re
        lines = content.split('\n')
        potential_topics = []
        
        # Heuristics
        for line in lines:
            line = line.strip()
            # 1. Headings (Short, All Caps, or starting capitals without ending dot)
            if 3 < len(line.split()) < 8 and re.match(r'^[A-Z]', line) and not line.endswith(('.', '?', '!')):
                potential_topics.append(line)
            # 2. Bullet points
            elif line.startswith(('-', '*', '•')) and len(line.split()) > 2:
                # Remove Bullet
                clean_line = re.sub(r'^[\-\*•\s]+', '', line).strip()
                if 2 < len(clean_line.split()) < 10:
                    potential_topics.append(clean_line)
            # 3. Lines ending with ":"
            elif line.endswith(':') and len(line.split()) < 6:
                potential_topics.append(line.rstrip(':').strip())

        # If still too few, break into paragraph triggers
        if len(potential_topics) < 5:
            paragraphs = content.split('\n\n')
            for p in paragraphs:
                p = p.strip()
                if p:
                    words = p.split()
                    if len(words) > 10:
                        phrase = ' '.join(itertools.islice(words, 5))
                        if phrase not in potential_topics:
                             potential_topics.append(phrase)

        # Format
        topics_data = []
        for name in itertools.islice(potential_topics, 15):
             topics_data.append({
                 "topic_name": name,
                 "topic_content": f"Subtopic related to {name} extracted via text heuristics."
             })
        return topics_data

    def _generate_and_filter_batch(
        self, content_text, target_num, difficulty, bloom_level, question_type, teacher_note,
        selected_topic_names, resource_id, topic_ref,
        existing_questions, existing_texts, existing_embeddings, relax_topic
    ):
        """Helper to generate and filter a batch of questions based on given parameters."""
        import random
        import re
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine

        def _tfidf_max_sim(candidate: str, reference_texts: list) -> float:
            """Max TF-IDF cosine similarity between candidate and any reference text."""
            if not reference_texts:
                return 0.0
            try:
                corpus = list(reference_texts) + [candidate]
                vecs = TfidfVectorizer(min_df=1).fit_transform(corpus)
                scores = sklearn_cosine(vecs[-1], vecs[:-1])[0]
                return float(scores.max())
            except Exception:
                return 0.0

        def _tfidf_pair_sim(text_a: str, text_b: str) -> float:
            """TF-IDF cosine similarity between two texts."""
            if not text_a.strip() or not text_b.strip():
                return 0.0
            try:
                vecs = TfidfVectorizer(min_df=1).fit_transform([text_a, text_b])
                return float(sklearn_cosine(vecs[0], vecs[1])[0][0])
            except Exception:
                return 0.0

        
        # Select 3 random styles for this batch
        available_styles = [
            "Definition-based", "Scenario-based", "Application/Use-case", 
            "Comparison/Contrast", "Code/Output Analysis", "Cause and Effect"
        ]
        chosen_styles = random.sample(available_styles, 3)

        try:
            ai_questions = self.ai_service.generate_questions(
                content=content_text,
                num_questions=target_num,
                difficulty=difficulty,
                bloom_level=bloom_level,
                question_type=question_type,
                teacher_note=teacher_note,
                selected_topics=selected_topic_names,
                relax_topic=relax_topic,
                question_styles=chosen_styles
            )
        except Exception as e:
            logger.error(f"AI Generation batch failed: {e}")
            return []

        if not ai_questions:
            logger.error("AI returned empty list for batch")
            return []

        logger.info(f"AI batch returned {len(ai_questions)} questions")

        generated_questions = []
        rejection_count: int = 0
        max_rejections: int = 3
        
        def _normalize_stem(text: str) -> str:
            desc = str(text).lower()
            desc = re.sub(r'^(what is|how does|which of the following|why is|explain the|describe the|what does|identify the|define)\s+', '', desc)
            desc = re.sub(r'[^a-z0-9]', '', desc)
            return desc[:80]
            
        seen_stems = set(_normalize_stem(t) for t in existing_texts)

        for q_data in ai_questions:
            q_text = (q_data.get("question") or q_data.get("question_text") or "").strip()
            if not q_text:
                continue

            options_data = q_data.get("options")
            if not isinstance(options_data, dict):
                options_data = {}

            correct = q_data.get("correct_answer")
            if isinstance(correct, list):
                correct = ",".join(correct)
                
            skip_filters = rejection_count >= max_rejections  # type: ignore
            is_valid = True
            
            if not skip_filters:
                # 0. Structural Duplicate Filter (Stem Normalization)
                stem = _normalize_stem(q_text)
                if stem in seen_stems:
                    logger.info(f"Rejected Q: Structural duplicate detected. Stem: {stem}")
                    is_valid = False
                
                correct_str = str(correct).strip()
                correct_actual_text = options_data.get(correct_str, correct_str)

                # 1. Distractor Quality Validation & AI Repair
                opts_values = [str(v).strip() for k, v in options_data.items() if str(v).strip()]
                unique_opts = set([v.lower() for v in opts_values])
                
                if len(opts_values) != 4 or len(unique_opts) != 4:
                    logger.info(f"Insufficient unique options. Regenerating distractors for Q: {q_text[:50]}...")
                    try:
                        distractor_prompt = (
                            f"Question: '{q_text}'\n"
                            f"Correct Answer: '{correct_actual_text}'\n"
                            f"Generate 3 plausible but clearly INCORRECT domain-specific distractors that:\n"
                            f"- Belong to the same topic domain as the correct answer\n"
                            f"- Are semantically similar but factually wrong\n"
                            f"- Are similar in length to the correct answer\n"
                            f"Return ONLY a comma-separated list of the 3 distractors, nothing else."
                        )
                        distractors_response = self.ai_service.generate_explanation(distractor_prompt).strip()
                        distractors = [re.sub(r'^[\d\.\-\*]+\s*', '', d.strip()) for d in distractors_response.split(',')]
                        distractors = list(itertools.islice([d for d in distractors if d and d.lower() != correct_actual_text.lower()], 3))

                        if len(distractors) >= 2:
                            while len(distractors) < 3:
                                distractors.append("All of the above" if len(distractors) == 2 else "None of the above")
                            options_data = {
                                "A": correct_actual_text,
                                "B": distractors[0],
                                "C": distractors[1],
                                "D": distractors[2],
                            }
                            correct = "A"
                            correct_str = "A"
                        else:
                            logger.info("AI Distractor repair yielded < 2 distractors — rejecting.")
                            is_valid = False
                    except Exception as e:
                        logger.error(f"Distractor repair exception: {e}")
                        is_valid = False

                # 1b. Distractor Semantic Quality Filter (TF-IDF cosine)
                # Distractors must be domain-related but not near-identical to correct answer
                if is_valid:
                    try:
                        correct_str_key = str(correct).strip()
                        correct_answer_text = options_data.get(correct_str_key, correct_str_key)
                        distractor_texts = [
                            str(v).strip() for k, v in options_data.items()
                            if k != correct_str_key and str(v).strip()
                        ]
                        if distractor_texts and correct_answer_text:
                            valid_distractors = []
                            for dist_text in distractor_texts:
                                sim = _tfidf_pair_sim(correct_answer_text, dist_text)
                                if sim < 0.04:
                                    logger.info(f"Distractor too unrelated (sim={sim:.3f}): '{dist_text[:35]}'")
                                elif sim > 0.92:
                                    logger.info(f"Distractor too similar to answer (sim={sim:.3f}): '{dist_text[:35]}'")
                                else:
                                    valid_distractors.append(dist_text)

                            if len(valid_distractors) < 2:
                                logger.info(f"Only {len(valid_distractors)} semantically valid distractors — triggering repair.")
                                repair_prompt = (
                                    f"Question: '{q_text}'\n"
                                    f"Correct Answer: '{correct_answer_text}'\n"
                                    f"Generate 3 plausible but clearly INCORRECT domain-specific distractors.\n"
                                    f"Each must:\n- Belong to the SAME topic domain\n"
                                    f"- Be factually wrong but sound plausible\n"
                                    f"- Be similar in length to the correct answer\n"
                                    f"Return ONLY comma-separated distractors, no numbering."
                                )
                                repair_resp = self.ai_service.generate_explanation(repair_prompt).strip()
                                repaired = [
                                    re.sub(r'^[\d\.\-\*]+\s*', '', d.strip())
                                    for d in repair_resp.split(',')
                                    if d.strip() and d.strip().lower() != correct_answer_text.lower()
                                ][:3]
                                if len(repaired) >= 2:
                                    while len(repaired) < 3:
                                        repaired.append(repaired[-1] + " (variant)")
                                    options_data = {
                                        "A": correct_answer_text,
                                        "B": repaired[0], "C": repaired[1], "D": repaired[2],
                                    }
                                    correct = "A"
                                    correct_str = "A"
                                    logger.info("Semantic distractor repair succeeded.")
                                else:
                                    logger.info("Semantic distractor repair insufficient — accepting originals.")
                            elif len(valid_distractors) == 2:
                                # Patch 1 bad distractor with a neutral fallback
                                valid_distractors.append("None of the above")
                                options_data = {
                                    "A": correct_answer_text,
                                    "B": valid_distractors[0], "C": valid_distractors[1], "D": valid_distractors[2],
                                }
                                correct = "A"; correct_str = "A"
                    except Exception as dist_e:
                        logger.warning(f"Distractor semantic filter failed (non-fatal): {dist_e}")

                # 1c. TF-IDF Cosine Duplicate Pre-filter (fast surface-level check)
                if is_valid and existing_texts:
                    tfidf_sim = _tfidf_max_sim(q_text, list(existing_texts))
                    if tfidf_sim > 0.80:
                        logger.info(f"Rejected Q (TF-IDF sim={tfidf_sim:.2f} > 0.80): '{q_text[:50]}'")
                        is_valid = False

                # 2. Context Validation (SKIP IF RELAX_TOPIC == TRUE)
                if is_valid and selected_topic_names and not relax_topic:
                    keywords = []
                    for t in selected_topic_names:
                        keywords.extend([w.lower() for w in str(t).split() if len(w) > 3])
                    
                    if keywords:
                        q_lower = q_text.lower()
                        opts_text = " ".join([str(v) for v in options_data.values()]).lower()
                        has_keyword = any(kw in q_lower or kw in opts_text for kw in keywords)
                        if not has_keyword:
                            logger.info(f"Rejected Q: Failed context validation. Keywords {keywords} not in Question or Options.")
                            is_valid = False
                            
                # 3. Semantic Duplicate Check
                if is_valid and similarity_model and existing_embeddings is not None and len(existing_texts) > 0:
                    try:
                        new_emb = similarity_model.encode(q_text, convert_to_tensor=True)
                        cosine_scores = util.cos_sim(new_emb, existing_embeddings)[0]
                        max_score_idx = cosine_scores.argmax().item()
                        max_score = cosine_scores[max_score_idx].item()
                        
                        if max_score > 0.70:
                            similar_q = existing_questions[max_score_idx]
                            logger.info(f"Similarity {max_score:.2f} > 0.70 with Q: {similar_q.question_text[:30]}... Triggering Soft Rewrite.")
                            
                            rewrite_prompt = f"""
                            Rewrite the following question to change its phrasing and focus (e.g., from definition to application, case-study, or comparison).
                            Ensure it tests the same overarching core concept but statement statement differs distinctly.
                            Options and correct answer must match this new framing context.
                            
                            Original Question: {q_text}
                            Options: {json.dumps(options_data)}
                            Correct Answer: {correct_actual_text}
                            
                            Return response ONLY as valid JSON without extra text:
                            {{
                              "question": "...",
                              "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
                              "correct_answer": "A"
                            }}
                            """
                            try:
                                rw_output = self.ai_service.generate_explanation(rewrite_prompt).strip()
                                cleaned_rw = rw_output
                                
                                # Extract JSON robustly
                                if "```json" in cleaned_rw:
                                     cleaned_rw = cleaned_rw.split("```json")[1].split("```")[0].strip()
                                elif "```" in cleaned_rw:
                                     cleaned_rw = cleaned_rw.split("```")[1].split("```")[0].strip()
                                else:
                                     pos_s = cleaned_rw.find('{')
                                     pos_e = cleaned_rw.rfind('}')
                                     if pos_s != -1 and pos_e != -1:
                                          cleaned_rw = cleaned_rw[pos_s:pos_e+1].strip()
                                          
                                rw_data = json.loads(cleaned_rw)
                                if "question" in rw_data and "options" in rw_data:
                                     q_text = rw_data["question"]
                                     options_data = rw_data["options"]
                                     if "correct_answer" in rw_data:
                                          correct = rw_data["correct_answer"]
                                     logger.info(f"Soft Rewrite applied successfully. New Q: {q_text[:30]}...")
                                else:
                                     logger.info("Soft Rewrite JSON missing fields. Rejecting.")
                                     is_valid = False
                            except Exception as rw_e:
                                logger.error(f"Soft Rewrite failed: {rw_e}. Rejecting.")
                                is_valid = False
                    except Exception as e:
                        logger.error(f"Semantic check failed: {e}")
                        
                # 4. Ambiguous Reference Validation
                if is_valid:
                    forbidden_phrases = [
                        # Generic document references
                        "the provided resource", "the given text", "the following content",
                        "the given content", "the above content", "the text above",
                        "the given document", "this document",
                        # Generic algorithm/method references
                        "the algorithm", "this algorithm", "the above algorithm",
                        "the method", "this method", "the above method",
                        "the process", "this process", "the above process",
                        # Generic paragraph/passage references
                        "the given paragraph", "this paragraph", "the passage",
                        # Vague relational references
                        "as mentioned above", "as described above",
                    ]
                    q_lower = q_text.lower()
                    for phrase in forbidden_phrases:
                        if phrase in q_lower:
                            logger.info(f"Rejected Q: ambiguous reference '{phrase}'. Q: {q_text[:60]}")
                            is_valid = False
                            break

                # 4b. Option Length Balance Check (best-effort, non-blocking)
                if is_valid:
                    try:
                        opt_lengths = [len(str(v)) for v in options_data.values()]
                        length_std = float(np.std(opt_lengths)) if opt_lengths else 0.0
                        if length_std > 40:
                            logger.info(f"Option length imbalance (stddev={length_std:.1f}) — attempting soft balance.")
                            try:
                                balance_prompt = (
                                    f"The following MCQ options have very uneven lengths. "
                                    f"Rewrite all 4 options so they are similar in length (within ~20 words of each other) "
                                    f"while keeping the same meaning. Correct answer is {correct}.\n"
                                    f"Question: {q_text}\n"
                                    f"Options: {json.dumps(options_data)}\n"
                                    f'Return ONLY valid JSON: {{"A": "...", "B": "...", "C": "...", "D": "..."}}'
                                )
                                bal_resp = self.ai_service.generate_explanation(balance_prompt).strip()
                                if "```json" in bal_resp:
                                    bal_resp = bal_resp.split("```json")[1].split("```")[0].strip()
                                elif "```" in bal_resp:
                                    bal_resp = bal_resp.split("```")[1].split("```")[0].strip()
                                else:
                                    ps, pe = bal_resp.find('{'), bal_resp.rfind('}')
                                    if ps != -1 and pe != -1:
                                        bal_resp = bal_resp[ps:pe+1].strip()
                                bal_data = json.loads(bal_resp)
                                if isinstance(bal_data, dict) and len(bal_data) == 4:
                                    options_data = bal_data
                                    logger.info("Option length balance repair applied.")
                            except Exception as bal_e:
                                logger.warning(f"Option balance repair failed (non-fatal): {bal_e}")
                    except Exception as len_e:
                        logger.warning(f"Option length check error (non-fatal): {len_e}")

                if is_valid:
                    seen_stems.add(stem)

            if not is_valid:
                rejection_count += 1  # type: ignore
                continue

            new_q = GeneratedQuestion(
                resource_id=resource_id,
                topic_id=topic_ref,
                question_text=q_text,
                options=json.dumps(options_data),
                correct_answer=correct,
                bloom_level=q_data.get('bloom_level') or bloom_level,
                difficulty=q_data.get('difficulty') or difficulty,
                question_type=question_type,
                explanation=q_data.get('explanation')
            )
            generated_questions.append(new_q)
            existing_texts.append(q_text)  # Update so subsequent questions in this batch are checked

        return generated_questions

    def generate_quiz(self, resource_id: int, user_id: int, **params):
        """
        Generates a quiz using AI and stores questions in DB.
        """

        resource = Resource.query.get_or_404(resource_id)

        if resource.resource_type == 'user_upload' and resource.created_by != user_id:
            raise PermissionError("You do not have permission to access this resource.")

        topic_mode = params.get('topic_mode')
        topic_id = params.get('topic_id')
        topic_ids = params.get('topic_ids', [])

        content_text = resource.content
        topic_ref = None
        selected_topic_names = []

        if topic_mode == 'topic':
            # Handle multiple topics if provided
            if topic_ids:
                topics = ResourceTopic.query.filter(
                    ResourceTopic.resource_id == resource.id,
                    ResourceTopic.id.in_(topic_ids)
                ).all()
                
                if topics:
                    # Concatenate content from all selected topics
                    topic_contents = [t.topic_content for t in topics if t.topic_content and len(t.topic_content.strip()) >= 50]
                    if topic_contents:
                        content_text = "\n\n".join(topic_contents)
                        selected_topic_names = [t.topic_name for t in topics]
                        # For generated_question record, we'll use the first topic as ref or None
                        topic_ref = topics[0].id
                        logger.info(f"Using content from {len(topic_contents)} selected subtopics.")
                    else:
                        logger.warning("Selected topics content is too short. Falling back to full resource content.")
                else:
                    logger.warning("No valid topics found for provided IDs. Falling back to full resource content.")
            
            # Backward compatibility for single topic_id
            elif topic_id and str(topic_id).lower() not in ['none', '', 'null']:
                try:
                    topic_id_int = int(topic_id)
                    topic = ResourceTopic.query.filter_by(resource_id=resource.id, id=topic_id_int).first()
                    
                    if topic:
                        if topic.topic_content and len(topic.topic_content.strip()) >= 50:
                            content_text = topic.topic_content
                            topic_ref = topic.id
                            selected_topic_names = [topic.topic_name]
                            logger.info(f"Using subtopic content for Topic ID: {topic_ref}")
                        else:
                            logger.warning(f"Topic content for ID {topic_id_int} is too short. Falling back to full resource content.")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid topic_id format '{topic_id}': {e}.")

        if not content_text or len(content_text.strip()) < 50:
            raise ValueError("Insufficient content available for quiz generation.")

        target_num = int(params.get('num_questions', 5))
        difficulty = params.get('difficulty', 'medium')
        base_bloom = params.get('bloom_level', 'understand')
        question_type = params.get('question_type', 'MCQ')
        teacher_note = params.get('teacher_note')

        # Pre-fetch existing questions for similarity check to avoid N+1 queries
        existing_questions = GeneratedQuestion.query.filter_by(resource_id=resource.id).all()
        existing_texts = [q.question_text for q in existing_questions if q.question_text]
        existing_embeddings = None
        
        if similarity_model and existing_texts:
            existing_embeddings = similarity_model.encode(existing_texts, convert_to_tensor=True)

        generated_questions = []

        # STAGE 1 - Strict Generation
        logger.info("Starting Stage 1: Strict Generation")
        batch_1 = self._generate_and_filter_batch(
            content_text, target_num, difficulty, base_bloom, question_type, teacher_note, 
            selected_topic_names, resource.id, topic_ref, 
            existing_questions, existing_texts, existing_embeddings, False
        )
        generated_questions.extend(batch_1)

        # STAGE 2 - Relax Bloom constraint
        if len(generated_questions) < target_num:
            missing = target_num - len(generated_questions)
            logger.info(f"Stage 1 hit {len(generated_questions)}/{target_num}. Stage 2: Relaxing Bloom Level for {missing} questions.")
            
            relaxed_bloom = f"{base_bloom} or ANY suitable level"
            batch_2 = self._generate_and_filter_batch(
                content_text, missing, difficulty, relaxed_bloom, question_type, teacher_note, 
                selected_topic_names, resource.id, topic_ref, 
                existing_questions, existing_texts, existing_embeddings, False
            )
            # Add new texts/embeddings to avoid duplicating within the same run (optional, but skipping here to keep simple since we only generate a small delta)
            generated_questions.extend(batch_2)

        # STAGE 3 - Relax Topic constraint
        if len(generated_questions) < target_num:
            missing = target_num - len(generated_questions)
            logger.info(f"Stage 2 hit {len(generated_questions)}/{target_num}. Stage 3: Relaxing Topic Filter for {missing} questions.")
            
            relaxed_bloom = f"{base_bloom} or ANY suitable level"
            batch_3 = self._generate_and_filter_batch(
                content_text, missing, difficulty, relaxed_bloom, question_type, teacher_note, 
                selected_topic_names, resource.id, topic_ref, 
                existing_questions, existing_texts, existing_embeddings, True
            )
            generated_questions.extend(batch_3)

        # STAGE 4 - Guaranteed Target Regeneration Loop
        retries = 0
        while len(generated_questions) < target_num:
            missing = target_num - len(generated_questions)
            logger.info(f"Looping to generate {missing} more questions (Retry {retries+1})")
            
            relaxed_bloom = f"{base_bloom} or ANY suitable level"
            batch_fallback = self._generate_and_filter_batch(
                content_text, missing, difficulty, relaxed_bloom, question_type, teacher_note,
                selected_topic_names, resource.id, topic_ref,
                existing_questions, existing_texts, existing_embeddings, True
            )
            generated_questions.extend(batch_fallback)
            retries += 1
            
            # Break runaway loop gracefully, though the while condition should naturally terminate
            if retries >= 10:
                logger.error("Breaking runaway generation loop.")
                missing = target_num - len(generated_questions)
                logger.warning(f"Generator failed to meet target. Creating {missing} fallback template questions.")
                topic_str = str(list(selected_topic_names)[0]) if selected_topic_names else "the provided resource content"
                fallback_templates = [
                    {
                        "q": f"Identify the correct statement regarding {topic_str} based on the content.",
                        "opts": {
                             "A": f"It describes the primary definition of {topic_str}",
                             "B": "It is an unrelated detail",
                             "C": "It is a secondary attribute",
                             "D": "None of the above"
                        }
                    },
                    {
                        "q": f"What is the core purpose or intended output of {topic_str}?",
                        "opts": {
                             "A": f"To process mechanics related to {topic_str}",
                             "B": "To increase buffer size",
                             "C": "To create a simple loop",
                             "D": "To cancel execution"
                        }
                    },
                    {
                        "q": f"Define the term {topic_str} as it is used in the context of the resource.",
                        "opts": {
                             "A": f"A key mechanism for structuring {topic_str}",
                             "B": "An external library inclusion",
                             "C": "A database schema table",
                             "D": "A standalone string variable"
                        }
                    }
                ]
                
                for i in range(missing):
                    tpl = fallback_templates[i % len(fallback_templates)]
                    fallback_q = GeneratedQuestion(
                        resource_id=resource.id,
                        topic_id=topic_ref,
                        question_text=tpl["q"],
                        options=json.dumps(tpl["opts"]),
                        correct_answer="A",
                        bloom_level=base_bloom,
                        difficulty=difficulty,
                        question_type="MCQ",
                        explanation="Fallback template generated due to AI generation limits."
                    )
                    generated_questions.append(fallback_q)
                break
                
        # Truncate to exact required number of questions
        generated_questions = list(itertools.islice(generated_questions, target_num))

        if not generated_questions:
            logger.error("No valid questions parsed from AI response after all stages")
            raise RuntimeError("AI did not return any valid questions.")

        logger.info(f"Saving {len(generated_questions)} combined questions to database")

        for new_q in generated_questions:
            db.session.add(new_q)
            
        db.session.commit()

        quiz = Quiz(
            user_id=user_id,
            resource_id=resource.id,
            total_questions=len(generated_questions),
            mode=topic_mode,
            bloom_level=params.get('bloom_level'),
            difficulty=params.get('difficulty'),
            teacher_note=params.get('teacher_note'),
            passing_score=float(params.get('passing_score', 0.0))
        )

        quiz.questions.extend(generated_questions)
        db.session.add(quiz)
        db.session.commit()

        logger.info(f"Quiz created successfully: ID {quiz.id}")

        return quiz.id

    def generate_custom_quiz(self, resource_id: int, teacher_note: str, admin_id: int):
        """
        Specialized quiz generation for Admin Assignments.
        """
        params = {
            'topic_mode': 'full',
            'num_questions': 5,
            'difficulty': 'medium',
            'bloom_level': 'apply',
            'question_type': 'MCQ',
            'teacher_note': teacher_note,
            'passing_score': 0.0
        }
        
        # generate_quiz returns an attempt_id, but for assignments we want the quiz_id.
        # Let's modify generate_quiz to be more flexible or just get the quiz from the attempt.
        attempt_id = self.generate_quiz(resource_id=resource_id, user_id=admin_id, **params)
        attempt = QuizAttempt.query.get(attempt_id)
        return attempt.quiz_id

    def get_topics(self, resource_id: int):
        topics = ResourceTopic.query.filter_by(resource_id=resource_id).all()
        logger.info(f"get_topics looked up resource {resource_id}. Found {len(topics)} topics in DB.")
        
        if not topics:
            logger.info(f"No topics found in DB for resource {resource_id}. Triggering extraction process.")
            self.process_resource_topics(resource_id)
            topics = ResourceTopic.query.filter_by(resource_id=resource_id).all()

        # Level 3 — Forced Fallback (Ensure at least 5 topics)
        if len(topics) < 5:
            logger.info(f"Resource {resource_id} has {len(topics)} topics. Level 3 fallback triggering to meet minimum 5.")
            fallbacks = ["Introduction", "Core Concepts", "Examples", "Applications", "Summary"]
            existing = {t.topic_name.lower() for t in topics}
            added_any = False
            for f_name in fallbacks:
                if len(topics) >= 5:
                    break
                if f_name.lower() not in existing:
                    new_topic = ResourceTopic(
                        resource_id=resource_id,
                        topic_name=f_name,
                        topic_content=f"Generic overview subtopic for {f_name} of the resource."
                    )
                    db.session.add(new_topic)
                    topics.append(new_topic)
                    added_any = True
            if added_any:
                db.session.commit()
                # Refetch to ensure IDs populated securely
                topics = ResourceTopic.query.filter_by(resource_id=resource_id).all()
                
        return topics

    def submit_quiz(self, attempt_id: int, user_answers: dict):
        """
        Calculates score and updates quiz attempt.
        user_answers: dict {question_id: selected_option(s)}
        """
        attempt = QuizAttempt.query.get_or_404(attempt_id)
        
        if attempt.completed_at:
             total_correct = AttemptAnswer.query.filter_by(attempt_id=attempt.id, is_correct=True).count()
             return {
                "score": attempt.total_score,
                "total_correct": total_correct,
                "total_questions": len(attempt.quiz.questions)
            }

        total_correct = 0
        total_questions = len(attempt.quiz.questions)
        
        AttemptAnswer.query.filter_by(attempt_id=attempt.id).delete()
        
        for question in attempt.quiz.questions:
            user_ans = user_answers.get(str(question.id)) or user_answers.get(question.id)
            
            is_correct = self._calculate_score(question, user_ans)
            
            if is_correct:
                total_correct += 1
                
            if isinstance(user_ans, list):
                stored_ans = ",".join(map(str, user_ans))
            else:
                stored_ans = str(user_ans) if user_ans is not None else None

            attempt_answer = AttemptAnswer(
                attempt_id=attempt.id,
                question_id=question.id,
                selected_answer=stored_ans,
                is_correct=is_correct
            )
            db.session.add(attempt_answer)
            
        if total_questions > 0:
            attempt.total_score = (total_correct / total_questions) * 100.0
        else:
            attempt.total_score = 0.0
            
        # Update AssignmentAttempt if this quiz is part of an assignment
        assignments = Assignment.query.filter_by(quiz_id=attempt.quiz_id).all()
        for assignment in assignments:
            status = AssignmentAttempt.query.filter_by(
                assignment_id=assignment.id, 
                user_id=attempt.user_id
            ).first()
            
            if not status:
                status = AssignmentAttempt(
                    assignment_id=assignment.id,
                    user_id=attempt.user_id,
                    is_submitted=False
                )
                db.session.add(status)
            
            status.score = attempt.total_score
            status.time_taken = attempt.time_taken
            status.completed_at = attempt.completed_at
            status.quiz_attempt_id = attempt.id
            status.is_submitted = True

            # Also update AssignmentUser status
            au = AssignmentUser.query.filter_by(assignment_id=assignment.id, user_id=attempt.user_id).first()
            if au:
                au.status = 'completed'

        db.session.commit()
        
        return {
            "score": attempt.total_score,
            "total_correct": total_correct,
            "total_questions": total_questions
        }

    def _calculate_score(self, question, user_answer):
        """
        Helper to validate answers based on question type.
        """
        if user_answer is None or user_answer == "":
            return False
            
        q_type = question.question_type or "MCQ" # 
        correct_answer = question.correct_answer
        
        try:
            if q_type == "MCQ":
                return str(user_answer).strip().lower() == str(correct_answer).strip().lower()
                
            elif q_type == "MSQ":
             
                if isinstance(user_answer, str):
                    user_set = set(x.strip() for x in user_answer.split(","))
                elif isinstance(user_answer, list):
                    user_set = set(str(x).strip() for x in user_answer)
                else:
                    return False
                    
                correct_set = set(x.strip() for x in str(correct_answer).split(","))
                return user_set == correct_set
                
            elif q_type == "NAT":
                
                try:
                    return abs(float(user_answer) - float(correct_answer)) < 0.01
                except ValueError:
                   
                    return str(user_answer).strip().lower() == str(correct_answer).strip().lower()
                    
            return False
        except Exception as e:
            logger.error(f"Error calculating score for Q{question.id}: {e}")

    def analyze_attempt_with_ai(self, attempt_id: int):
        """
        Generates AI-based explanations for a completed quiz attempt.
        Returns a list of analysis dictionaries.
        """
        attempt = QuizAttempt.query.get_or_404(attempt_id)
        if not attempt.completed_at:
            return []

        # Collect data for all questions to batch them into one AI call
        questions_to_analyze = []
        for answer in attempt.answers:
            question = answer.question
            options = json.loads(question.options) if question.options else {}
            questions_to_analyze.append({
                "id": question.id,
                "text": question.question_text,
                "type": question.question_type or "MCQ",
                "options": options,
                "correct_answer": question.correct_answer,
                "user_answer": answer.selected_answer,
                "is_correct": "Yes" if answer.is_correct else "No"
            })

        if not questions_to_analyze:
            return []

        # Build ONE combined prompt for structured JSON
        prompt = f"""
Analyze the following quiz questions and provide clear explanations for each.
Return your response ONLY as a JSON object where keys are the question IDs (as strings) and values are the explanations.

Format example:
{{
  "1": "Explanation for question 1...",
  "2": "Explanation for question 2..."
}}

Requirements for each explanation:
1. Explain why the correct answer is indeed correct.
2. If the user was wrong, clarify their mistake without being discouraging.
3. Provide a brief conceptual clarification of the topic involved.
4. Return ONLY plain text for the explanation value. No further nesting.
5. Keep each explanation under 150 words.

Questions to analyze:
{json.dumps(questions_to_analyze, indent=2)}
"""
        
        # Single AI call per result page
        try:
            raw_response = self.ai_service.generate_explanation(prompt)
            logger.info(f"AI Batch Response received. Raw Length: {len(raw_response)} chars")
            
            explanations_map = {}
            if raw_response:
                # 2. Clean response before parsing
                cleaned_string = raw_response.strip()
                
                # If response contains ```json or ``` blocks, extract content inside.
                if "```json" in cleaned_string:
                    cleaned_string = cleaned_string.split("```json")[1].split("```")[0].strip()
                elif "```" in cleaned_string:
                    cleaned_string = cleaned_string.split("```")[1].split("```")[0].strip()
                else:
                    # Find first "{" and last "}" In string
                    start = cleaned_string.find('{')
                    end = cleaned_string.rfind('}')
                    if start != -1 and end != -1:
                        cleaned_string = cleaned_string[start:end+1].strip()

                logger.info(f"Cleaned JSON String: {cleaned_string}")
                logger.info(f"Cleaned JSON Length: {len(cleaned_string)} chars")

                # 4. Try: parsed = json.loads(cleaned_string)
                try:
                    explanations_map = json.loads(cleaned_string)
                    logger.info("Parsing successful.")
                except (ValueError, json.JSONDecodeError) as e:
                    logger.error(f"Failed to parse AI batch response as JSON: {e}")
                    # If it fails, explanations_map remains {} which will trigger fallback per question
            else:
                logger.warning("AI returned empty raw response.")

        except Exception as e:
            logger.error(f"AI Service call failed during batch analysis: {e}")
            explanations_map = {}

        # Map results back to the expected return structure
        analysis_data = []
        for answer in attempt.answers:
            question = answer.question
            q_id_str = str(question.id)
            
            # Use explanation from map, or fallback message
            explanation = None
            if isinstance(explanations_map, dict):
                explanation = explanations_map.get(q_id_str)
            if not explanation or not isinstance(explanation, str):
                explanation = "Explanation unavailable."
            
            analysis_data.append({
                "question_id": question.id,
                "question_text": question.question_text,
                "options": json.loads(question.options) if question.options else {},
                "correct_answer": question.correct_answer,
                "user_answer": answer.selected_answer,
                "is_correct": answer.is_correct,
                "explanation": explanation
            })
            
        return analysis_data