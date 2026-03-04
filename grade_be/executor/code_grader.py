# code_grader.py

"""
Module responsible for generating AI-based grading results for code submissions
based on public test cases and the original problem description.
"""

import logging
import json
from typing import List, Dict, Any, Union
from .prompts.grading_prompts import build_grading_prompt

import asyncio
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from centralised_llm.src.llm_manager import handle_request

logger = logging.getLogger(__name__)


def generate_grading_json(
    code: str,
    question: str,
    public_testcases: List[Dict[str, str]]
) -> Union[Dict[str, Any], str, None]:
    """
    Generates grading feedback for a given code submission using AI.

    Builds a grading prompt using the question description and public test cases,
    then sends the prompt to the AI fallback system to get a structured grading response.
    """
    logger.info("🔹 Constructing grading prompt from public testcases.")
    prompt = build_grading_prompt(code, question, public_testcases)
    logger.info("🔸 Sending prompt to AI fallback system.")

    req1 = json.dumps({
        "model": "gemini",  # or mistralai, gemini, etc.
        "prompt": prompt,
        "parameters": {
            "temperature": 0.8,
            "model": "gemini-2.0-flash",
        },
    })

    try:
        res = asyncio.run(handle_request(req1))
    except Exception as e:
        logger.error(f"❌ Exception during handle_request: {e}")
        return None

    print("-----------------------------------------------------------------------------")
    print("AI Response: ", res)
    print("-----------------------------------------------------------------------------")

    if res is None:
        return None

    # If already a dictionary, return directly
    if isinstance(res, dict) and 'response' in res:
        res = res['response']

    # Otherwise, try to parse as JSON
    try:
        return json.loads(res)
    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ Could not parse grading response as JSON: {e}")
        return res
