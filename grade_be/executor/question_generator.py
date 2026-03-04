from rest_framework.response import Response
from rest_framework.request import Request
import json
import logging
import random
import time
from sentence_transformers import SentenceTransformer, util
from typing import Dict, Any, List, Optional
import asyncio
import os
import sys
import re

# Add parent directory to path to import centralised_llm
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from .models import Question, Company, Topic, TestCase
from .serializers import GenerateQuestionInputSerializer
from .prompts.question_prompts import build_question_generation_prompt
from .llm_utils import clean_generated_content
from centralised_llm.src.llm_manager import handle_request

logger = logging.getLogger(__name__)
# Initialize embedding model once at module level
model = SentenceTransformer('all-MiniLM-L6-v2')

def create_question_from_data(data: Dict[str, Any], topic_obj: Topic) -> Question:
    question = Question.objects.create(
        title=data.get("title", "Untitled"),
        description=data.get("description", ""),
        sample_input=data.get("sample_input", ""),
        sample_output=data.get("sample_output", ""),
        explanation=data.get("explanation", ""),
        constraints=data.get("constraints", ""),
        testcase_description=data.get("testcase_description", ""),
        difficulty=data.get("difficulty", "easy"),
        year_asked=data.get("year_asked", None),
    )
    question.topics.add(topic_obj)
    for topic_name in data.get("topics", []):
        t_obj, _ = Topic.objects.get_or_create(name=topic_name)
        question.topics.add(t_obj)
    for company_name in data.get("companies", []):
        c_obj, _ = Company.objects.get_or_create(name=company_name)
        question.companies.add(c_obj)
    return question

def generate_questions_logic(request: Request) -> Response:
    logger.info("Received POST request to generate questions.")
    serializer = GenerateQuestionInputSerializer(data=request.data)

    if not serializer.is_valid():
        logger.error("Invalid serializer input: %s", serializer.errors)
        return Response(serializer.errors, status=400)

    topic_name = serializer.validated_data['topic']
    difficulty = serializer.validated_data['difficulty']
    logger.info(f"Topic: {topic_name}, Difficulty: {difficulty}")

    # Fetch existing questions to prevent duplicates
    existing_questions = Question.objects.filter(
        topics__name=topic_name,
        difficulty=difficulty
    ).values_list('title', flat=True)
    existing_titles = list(existing_questions)
    
    # Only encode if there are existing titles to compare against
    existing_embeddings = None
    if existing_titles:
        existing_embeddings = model.encode(existing_titles, convert_to_tensor=True)

    # --- UPDATED STRATEGY: 1 at a time, high attempts ---
    target_count = 7      # Goal
    max_attempts = 20     # Give it plenty of tries
    # ----------------------------------------------------
    
    attempt = 0
    generated_questions = []
    new_titles = []
    topic_obj, _ = Topic.objects.get_or_create(name=topic_name)

    while len(generated_questions) < target_count and attempt < max_attempts:
        attempt += 1
        logger.info(f"Attempt {attempt}: Generating question {len(generated_questions)+1}/{target_count}...")
        
        base_prompt = build_question_generation_prompt(topic_name, difficulty)
        
        # Build strict prompt for SINGLE question generation
        avoid_list = existing_titles + new_titles
        avoid_str = ", ".join(avoid_list[-30:]) if avoid_list else "None"
        
        enhanced_prompt = (
            f"{base_prompt}\n\n"
            f"STRICT OUTPUT RULES:\n"
            f"1. Generate exactly **ONE** coding question in valid JSON format.\n"
            f"2. Do NOT wrap the JSON in markdown blocks (no ```json ... ```).\n"
            f"3. Ensure the JSON is complete and valid. Do not cut off.\n"
            f"4. AVOID generating questions similar to: [{avoid_str}].\n"
            f"5. Return ONLY the JSON object."
        )
        
        req_payload = json.dumps({
            "model": "gemini", 
            "prompt": enhanced_prompt,
            "parameters": {
                "temperature": 0.8, # High creativity to avoid duplicates
                "model": "gemini-2.0-flash", 
                "max_tokens": 8192
            },
        })

        try:
            content = safe_async_call(handle_request(req_payload))
        except Exception as e:
            logger.error(f"Exception while calling handle_request: {e}")
            continue

        if not content:
            logger.warning("Model returned empty content.")
            continue

        try:
            # Handle potential dictionary wrap
            if isinstance(content, dict):
                if content.get('error'): 
                    logger.error(f"LLM Error: {content['error']}")
                    continue
                if 'response' in content:
                    content = content['response']
            
            # Cleaning
            content = extract_json_from_response(content)  
            content = auto_fix_json(content)

            # Parsing
            try:
                questions_json = json.loads(content)
                # Normalize to list
                if isinstance(questions_json, dict):
                     questions_json = [questions_json]
                elif not isinstance(questions_json, list):
                    logger.error("Parsed content is neither dict nor list")
                    continue
                    
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                logger.debug(f"Failed Content: {str(content)[:200]}...") 
                continue

        except Exception as e:
            logger.error(f"Failed to process content logic: {e}")
            continue

        # Process the SINGLE question (since batch size is effectively 1)
        for q in questions_json:
            try:
                new_title = q.get("title", "").strip()
                if not new_title:
                    continue

                # --- Semantic De-duplication ---
                all_titles = existing_titles + new_titles
                if all_titles:
                    all_embeddings = model.encode(all_titles, convert_to_tensor=True)
                    new_embedding = model.encode(new_title, convert_to_tensor=True)
                    
                    similarity_scores = util.cos_sim(new_embedding, all_embeddings)
                    if similarity_scores.max().item() > 0.85:
                        logger.info(f"Duplicate skipped: {new_title}")
                        continue
                # -------------------------------

                sample_io = q.get("sample_io", [])
                sample_input = sample_io[0].get("input", "") if sample_io else ""
                sample_output = sample_io[0].get("output", "") if sample_io else ""

                question_data = {
                    "title": new_title,
                    "description": q.get("description", ""),
                    "sample_input": sample_input,
                    "sample_output": sample_output,
                    "explanation": q.get("explanation", ""),
                    "constraints": q.get("constraints", ""),
                    "testcase_description": q.get("testcase_description", ""),
                    "difficulty": difficulty,
                    "year_asked": q.get("year_asked", None),
                    "topics": q.get("topics", []),
                    "companies": q.get("companies_asked", []),
                }

                question = create_question_from_data(question_data, topic_obj)

                for sample in sample_io:
                    TestCase.objects.create(
                        question=question,
                        input_data=sample.get("input", ""),
                        expected_output=sample.get("output", ""),
                        is_sample=True,
                        test_type="public"
                    )

                hidden_tests = q.get("test_cases", [])
                for test in hidden_tests:
                    TestCase.objects.create(
                        question=question,
                        input_data=test.get("input", ""),
                        expected_output=test.get("output", ""),
                        is_sample=False,
                        test_type="hidden"
                    )

                generated_questions.append({
                    'id': question.id,
                    'title': question.title,
                })
                new_titles.append(new_title)
                logger.info(f"Successfully generated: {new_title}")

                if len(generated_questions) >= target_count:
                    break
            except Exception as e:
                logger.error(f"Failed to save question '{new_title}': {e}")

    if len(generated_questions) == 0:
        return Response({"error": "No valid questions were generated."}, status=500)

    return Response({
        "message": f"Successfully generated {len(generated_questions)} questions.",
        "questions": generated_questions
    }, status=201)


def extract_json_from_response(content: str) -> str:
    if not isinstance(content, str):
        return str(content)
    content = content.strip()
    # Basic cleanup
    content = re.sub(r"^```(?:json)?", "", content, flags=re.IGNORECASE)
    content = re.sub(r"```$", "", content).strip()
    
    # Try to find list wrapper
    match_list = re.search(r"\[\s*{.*?}\s*.*?\]", content, re.DOTALL)
    if match_list: 
        return match_list.group(0)
    
    # Try to find single object wrapper
    match_obj = re.search(r"^\s*{.*?}\s*$", content, re.DOTALL)
    if match_obj: 
        return f"[{match_obj.group(0)}]" # Wrap single object in list for consistency
        
    return content

def auto_fix_json(content: str) -> str:
    content = content.strip()
    # Attempt to close open braces if truncated
    open_braces = content.count("{")
    close_braces = content.count("}")
    while open_braces > close_braces:
        content += "}"
        close_braces += 1
        
    open_brackets = content.count("[")
    close_brackets = content.count("]")
    while open_brackets > close_brackets:
        content += "]"
        close_brackets += 1
    return content

def safe_async_call(coroutine):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.ensure_future(coroutine)
        return loop.run_until_complete(coroutine)
    except RuntimeError:
        return asyncio.run(coroutine)
