# ocr_processor.py
import os
import io
import re
import base64
import json
import hashlib
from collections import defaultdict
from PIL import Image
# import fitz  # PyMuPDF
# import cv2
# import numpy as np
# from ultralytics import YOLO
from dotenv import load_dotenv
from google import genai  # <-- UPDATED
import time
from pydantic import BaseModel, Field, RootModel, ConfigDict, field_validator, ValidationInfo # <-- ADDED
from typing import List, Dict, Optional, Any, Tuple
import logging
from django.conf import settings
from pathlib import Path
from centralised_llm.src.llms.gemini_genai_llm import GeminiGradingClient, GenerateResponse

# NEW IMPORTS FOR TOKEN/COST METRICS
import csv
import math
import statistics
from datetime import datetime, timezone
from typing import Iterable

# NEW IMPORT: Added for safety settings (already present)
from google.genai.types import HarmCategory, HarmBlockThreshold

# --- NEW: PROMPT LOADER ---
PROMPT_DIR = settings.BASE_DIR / "ai_prompts"

def load_prompt(filename: str) -> str:
    """
    Loads a prompt from the ai_prompts directory.
    Prefers YAML files (.yaml) and extracts the 'prompt' field.
    Falls back to .txt files for backwards compatibility.
    """
    import yaml
    
    # Try YAML first (convert .txt to .yaml if needed)
    if filename.endswith('.txt'):
        yaml_filename = filename.replace('.txt', '.yaml')
    else:
        yaml_filename = filename
    
    yaml_path = PROMPT_DIR / yaml_filename
    txt_path = PROMPT_DIR / filename
    
    # Try YAML file first
    if yaml_path.exists():
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict) and 'prompt' in data:
                    logger.info(f"??? Loaded prompt from YAML: {yaml_filename}")
                    return data['prompt']
                else:
                    logger.warning(f"YAML file {yaml_filename} missing 'prompt' key, reading as raw text")
                    f.seek(0)
                    return f.read()
        except Exception as e:
            logger.error(f"Error parsing YAML {yaml_path}: {e}")
            raise
    
    # Fallback to TXT file
    if txt_path.exists():
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                logger.info(f"???? Loaded prompt from TXT (fallback): {filename}")
                return f.read()
        except Exception as e:
            logger.error(f"Error reading TXT {txt_path}: {e}")
            raise
    
    # Neither file exists
    logger.error(f"CRITICAL: Prompt file not found: {yaml_path} or {txt_path}")
    raise FileNotFoundError(f"Missing prompt file: {yaml_filename} or {filename}")
# --- END PROMPT LOADER ---

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- NEW: TOKEN/COST CONSTANTS ---
# Default pricing (per 1,000,000 tokens) - override with env vars if provided
DEFAULT_INPUT_PRICE_PER_1M = float(os.getenv("GEMINI_INPUT_PRICE_PER_1M", "0.30"))
DEFAULT_OUTPUT_PRICE_PER_1M = float(
    os.getenv("GEMINI_OUTPUT_PRICE_PER_1M", "2.50")
)


# --- NEW: TOKEN/COST CALCULATOR CLASS ---
class TokenCostCalculator:
    """Simple helper to convert token counts to USD cost using per-1M token rates."""

    def __init__(
        self,
        input_price_per_1m: float = DEFAULT_INPUT_PRICE_PER_1M,
        output_price_per_1m: float = DEFAULT_OUTPUT_PRICE_PER_1M,
    ):
        self.input_price_per_1m = float(input_price_per_1m)
        self.output_price_per_1m = float(output_price_per_1m)

    def input_cost(self, tokens: int) -> float:
        return (tokens / 1_000_000.0) * self.input_price_per_1m

    def output_cost(self, tokens: int) -> float:
        return (tokens / 1_000_000.0) * self.output_price_per_1m

    def total_cost(self, input_tokens: int, output_tokens: int) -> float:
        return self.input_cost(input_tokens) + self.output_cost(output_tokens)

# --- ADD THESE NEW PYDANTIC MODELS ---

class CriteriaBreakdown(BaseModel):
    """Represents the grading for a single criterion."""
    # Use this config to allow Pydantic to handle conversion gracefully
    model_config = ConfigDict(coerce_numbers_to_str=True)
    
    criterion: str = Field(description="EXACT criterion text from answer key.")
    allocated_marks: float = Field(description="Marks for this criterion from answer key.")
    obtained_marks: float = Field(description="Marks awarded based on student performance for this criterion.")
    feedback: str = Field(description="Specific academic feedback explaining grade for this criterion.")
    mistakes_found: List[str] = Field(description="Specific mistakes for this criterion.")

class GradingResult(BaseModel):
    """
    Defines the structured JSON output for a single graded question.
    """
    model_config = ConfigDict(coerce_numbers_to_str=True)
    
    question_number: str = Field(description="The question number, e.g., 'Q1a'.")
    allocated_marks: float = Field(description="The total marks allocated for this question.")
    obtained_marks: float = Field(description="The total marks awarded for this question. This MUST be the sum of marks from criteria_breakdown (if present) or a holistic score if not.")
    student_answer: Dict[str, Any] = Field(description="A JSON object representing the student's answer.")
    expected_answer: Dict[str, Any] = Field(description="A JSON object representing the expected answer.")
    
    diagram_comparison: Optional[str] = Field(default=None, description="Detailed comparison of student vs. reference diagrams, or null if no diagrams.")
    
    criteria_breakdown: Optional[List[CriteriaBreakdown]] = Field(
        default=None, 
        description="A breakdown of grading for each criterion. Use this ONLY if evaluation criteria were provided."
    )
    
    general_feedback: Optional[str] = Field(
        default=None, 
        description="Detailed feedback explaining the evaluation. Use this ONLY if evaluation criteria were NOT defined."
    )
    
    mistakes_identified: List[str] = Field(description="A comprehensive list of all specific mistakes found.")
    summary: str = Field(description="A concise, formal academic summary of performance, including key mistakes and overall feedback.")

    @field_validator('obtained_marks')
    @classmethod
    def validate_marks(cls, v):
        if v < 0:
            return 0.0
        return float(v)

class ConceptDetail(BaseModel):
    """Detailed mastery analysis for a single concept."""
    concept_name: str = Field(description="Name of the concept derived from the Answer Key.")
    mastery_class: str = Field(description="Performance class: 'High', 'Good', 'Basic', 'Partial', or 'Bad'.")
    concept_accuracy_percentage: float = Field(description="Student's accuracy score (0-100%) for this concept.")
    reasoning: str = Field(description="Brief reasoning for this assessment.")

class ConceptAnalysisResult(BaseModel):
    """Result schema for concept analysis."""
    question_number: Optional[str] = Field(None, description="The question number this analysis belongs to. Required for batch processing.")
    concepts: List[ConceptDetail] = Field(description="List of analyzed concepts with detailed scoring.")
    overall_confidence_percentage: float = Field(description="Overall confidence percentage (0-100) for the analysis.")
    overall_confidence_level: str = Field(description="Overall confidence level: 'High', 'Good', 'Basic', 'Partial', 'Bad'.")

class ConceptAnalysisBatchResult(BaseModel):
    """Result schema for batch concept analysis."""
    results: List[ConceptAnalysisResult]

class GradingResultList(BaseModel):
    root: List[GradingResult]

class StudentGrader:
    def __init__(self, answer_key_diagram_folder: str = None, answer_upload=None):
        # --- MODIFICATION ---
        # All the old genai.Client, config, and safety settings are removed
        # and replaced with our new client.
        try:
            self.client = GeminiGradingClient(model_name="gemini-3-flash-preview")
        except ValueError as e:
            logger.error(f"Failed to initialize GeminiGradingClient: {e}")
            raise
        # --- END MODIFICATION ---

        self.answer_key = {}
        self.answer_key_diagrams = {}
        self.answer_upload = answer_upload  # Store for combined metrics summary

        self.answer_key_diagram_folder = (
            Path(answer_key_diagram_folder)
            if answer_key_diagram_folder
            else Path("temp_answer_key_diagrams")
        )
        ip = float(os.getenv("GEMINI_INPUT_PRICE_PER_1M", DEFAULT_INPUT_PRICE_PER_1M))
        op = float(os.getenv("GEMINI_OUTPUT_PRICE_PER_1M", DEFAULT_OUTPUT_PRICE_PER_1M))
        self.cost_calculator = TokenCostCalculator(ip, op)
        self.metrics_rows: List[Dict[str, Any]] = []
        self.failed_call_metrics: List[Dict[str, Any]] = []  # Track failed/wasted API calls

    # ---------------------------
    # NEW: Token counting utilities
    # ---------------------------
    def _count_tokens_official(self, text_or_content: Any) -> int:
        """
        Use client.models.count_tokens to get official Gemini token counts.
        """
        try:
            if not text_or_content:
                return 0
            
            # --- FIX: Access the client's internal client ---
            # self.client is the GeminiGradingClient
            # self.client.client is the raw genai.Client
            ct = self.client.client.models.count_tokens(
                model=self.client.model_name, # Use the model name from the client
                contents=text_or_content
            )
            # --- END FIX ---
            
            return int(ct.total_tokens)
        
        except Exception as e:
            # fallback heuristic: ~4 characters per token
            logger.debug(f"count_tokens failed ({e}), using char heuristic.")
            try:
                s = (
                    text_or_content
                    if isinstance(text_or_content, str)
                    else json.dumps(text_or_content, ensure_ascii=False)
                )
                return max(0, math.ceil(len(s) / 4.0))
            except Exception:
                return 0

    def _count_tokens_for_text_parts(self, parts: Iterable[str]) -> int:
        """Count tokens for an iterable of text parts and return the sum."""
        total = 0
        for p in parts:
            total += self._count_tokens_official(p)
        return total

    # ---------------------------
    # NEW: Metrics logging utilities
    # ---------------------------
    def _split_prompt_components(
        self,
        prompt_text: str,
        student_answer_obj: Dict,
        expected_answer_prompt: Optional[str] = None,
    ) -> Tuple[str, str, str, str]:
        """
        Attempt to split prompt_text into (system_text, instruction_text, student_text, context_text)
        This tries to find the JSON serialized student_answer_obj inside the prompt and use expected_answer_prompt
        as context if provided. Fallback: everything in instruction_text.
        """
        system_text = ""
        instruction_text = prompt_text
        student_text = ""
        context_text = expected_answer_prompt or ""

        try:
            # Use compact separators to match JSON dump in prompt
            student_dump = json.dumps(
                student_answer_obj, indent=2, ensure_ascii=False
            )
            idx = prompt_text.find(student_dump)

            if idx != -1:
                start = idx
                end = idx + len(student_dump)
                student_text = prompt_text[start:end]
                # instruction is prompt without student_text and context_text (if present)
                temp = prompt_text.replace(student_text, "")
                if (
                    expected_answer_prompt
                    and expected_answer_prompt in temp
                ):
                    temp = temp.replace(expected_answer_prompt, "")
                    context_text = expected_answer_prompt
                instruction_text = temp.strip()
                # Try to detect a leading 'system' block if present (very heuristic)
                if instruction_text.startswith("You are Professor Sarah Mitchell"):
                    # heuristically take first ~200 chars as system prompt
                    system_text = instruction_text[:200].strip()
                    instruction_text = instruction_text[200:].strip()
            else:
                # fallback - leave everything in instruction_text
                instruction_text = prompt_text
        except Exception as e:
            logger.debug(f"_split_prompt_components failed: {e}")
            instruction_text = prompt_text

        return system_text, instruction_text, student_text, context_text

    def _log_metrics_for_question(
        self,
        question_num: str,
        prompt_text: str,
        student_answer_obj: Dict,
        expected_answer_prompt: Optional[str],
        response_text: str,
        num_student_images: int,
        num_reference_images: int,
        input_tokens: int,
        output_tokens: int,
        # --- FIX: Add this optional argument ---
        actual_total_cost: float = None 
    ) -> Dict[str, Any]:
        """
        Logs metrics. Now supports taking the actual cost from the client.
        """
        # Split components for breakdown logging
        system_text, instruction_text, student_text, context_text = (
            self._split_prompt_components(
                prompt_text, student_answer_obj, expected_answer_prompt
            )
        )

        # Estimate token breakdown
        total_text_len = len(system_text) + len(instruction_text) + len(student_text) + len(context_text)
        if total_text_len == 0: total_text_len = 1
        approx_text_tokens = self._count_tokens_official(prompt_text)
        
        system_tokens = int(approx_text_tokens * (len(system_text) / total_text_len))
        instruction_tokens = int(approx_text_tokens * (len(instruction_text) / total_text_len))
        student_tokens = int(approx_text_tokens * (len(student_text) / total_text_len))
        context_tokens = int(approx_text_tokens * (len(context_text) / total_text_len))

        total_tokens = input_tokens + output_tokens

        # --- FIX: Use actual cost if available ---
        if actual_total_cost is not None:
            total_cost = actual_total_cost
            # We default input/output split to 0/0 or N/A because the client 
            # gives us the final sum, which is what matters most.
            input_cost = 0.0 
            output_cost = 0.0
        else:
            # Fallback to the old calculator (e.g. for non-Gemini models)
            input_cost = self.cost_calculator.input_cost(input_tokens)
            output_cost = self.cost_calculator.output_cost(output_tokens)
            total_cost = input_cost + output_cost
        # --- END FIX ---

        row = {
            "utc_ts": datetime.now(timezone.utc).isoformat(),
            "question_num": question_num,
            "system_tokens": int(system_tokens),
            "instruction_tokens": int(instruction_tokens),
            "student_tokens": int(student_tokens),
            "context_tokens": int(context_tokens),
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "total_tokens": int(total_tokens),
            "input_cost_usd": float(input_cost),
            "output_cost_usd": float(output_cost),
            "total_cost_usd": float(total_cost),
            "num_student_images": int(num_student_images),
            "num_reference_images": int(num_reference_images),
        }

        self.metrics_rows.append(row)
        
        logger.info(
            f"???? [METRICS] {question_num}: input={input_tokens} "
            f"output={output_tokens} total={total_tokens} cost=${total_cost:.6f}"
        )
        return row

    def save_metrics_csv(self, csv_path: str) -> None:
        """Persist collected metrics to CSV. If no metrics, does nothing."""
        if not self.metrics_rows:
            logger.info("No metrics to save.")
            return
        p = Path(csv_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        keys = list(self.metrics_rows[0].keys())
        with open(p, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for r in self.metrics_rows:
                writer.writerow(r)
        logger.info(f"Saved metrics CSV to {p}")

    def print_metrics_summary(self) -> None:
        """Print an aggregate summary (totals, averages, percentiles)"""
        if not self.metrics_rows:
            logger.info("No metrics collected.")
            return

        total_requests = len(self.metrics_rows)
        input_tokens_list = [r["input_tokens"] for r in self.metrics_rows]
        output_tokens_list = [r["output_tokens"] for r in self.metrics_rows]
        total_tokens_list = [r["total_tokens"] for r in self.metrics_rows]
        total_input = sum(input_tokens_list)
        total_output = sum(output_tokens_list)
        total_cost = sum(r["total_cost_usd"] for r in self.metrics_rows)

        def pctile(data, p):
            if not data:
                return 0
            data_sorted = sorted(data)
            k = max(
                0,
                min(
                    len(data_sorted) - 1,
                    math.ceil(len(data_sorted) * p / 100) - 1,
                ),
            )
            return data_sorted[k]

        logger.info("==== ???? GRADING METRICS SUMMARY ====")
        logger.info(f"Captured requests: {total_requests}")
        logger.info(f"Total input tokens: {total_input:,}")
        logger.info(f"Total output tokens: {total_output:,}")
        logger.info(f"Total tokens: {total_input + total_output:,}")
        logger.info(f"Estimated total cost (USD): ${total_cost:.6f}")
        logger.info(
            f"Avg input tokens/request: {statistics.mean(input_tokens_list):.1f}"
        )
        logger.info(
            f"Avg output tokens/request: {statistics.mean(output_tokens_list):.1f}"
        )
        logger.info(
            f"P50 input: {pctile(input_tokens_list, 50):,}, P90 input: {pctile(input_tokens_list, 90):,}, P99 input: {pctile(input_tokens_list, 99):,}"
        )
        logger.info(
            f"P50 output: {pctile(output_tokens_list, 50):,}, P90 output: {pctile(output_tokens_list, 90):,}, P99 output: {pctile(output_tokens_list, 99):,}"
        )
        logger.info("====================================")
        
        # Log wasted costs from failed batches
        if self.failed_call_metrics:
            failed_cost = sum(f['total_cost'] for f in self.failed_call_metrics)
            failed_tokens = sum(f['input_tokens'] + f['output_tokens'] for f in self.failed_call_metrics)
            logger.info("==== ?????? FAILED/WASTED API CALLS ====")
            logger.info(f"Failed batches: {len(self.failed_call_metrics)}")
            logger.info(f"Wasted tokens: {failed_tokens:,}")
            logger.info(f"Wasted cost (USD): ${failed_cost:.6f}")
            for f in self.failed_call_metrics:
                logger.warning(f"  ??? Batch {f['batch_id']}: ${f['total_cost']:.6f} ({f['input_tokens']:,} in / {f['output_tokens']:,} out) - {f['error']}")
            logger.info("====================================")

    def save_metrics_to_db(self, answer_upload) -> None:
        """Save grading metrics directly to the AIMetrics database model."""
        from .models import AIMetrics
        from datetime import datetime, timezone as tz
        
        if not self.metrics_rows:
            logger.info("No grading metrics to save to DB.")
            return
        
        try:
            # Clear existing grading metrics for this upload
            AIMetrics.objects.filter(answer_upload=answer_upload, process_type='GRADING').delete()
            
            # Create new metrics records
            metrics_objs = []
            for row in self.metrics_rows:
                metrics_objs.append(AIMetrics(
                    answer_upload=answer_upload,
                    process_type='GRADING',
                    identifier=row.get('question_num', 'Unknown'),
                    input_tokens=int(row.get('input_tokens', 0)),
                    output_tokens=int(row.get('output_tokens', 0)),
                    total_tokens=int(row.get('total_tokens', 0)),
                    total_cost_usd=float(row.get('total_cost_usd', 0)),
                    timestamp=datetime.now(tz.utc)
                ))
            
            AIMetrics.objects.bulk_create(metrics_objs)
            logger.info(f"??? Saved {len(metrics_objs)} grading metrics to DB for AnswerUpload {answer_upload.id}")
            
        except Exception as e:
            logger.error(f"Failed to save grading metrics to DB: {e}", exc_info=True)

    def get_metrics_totals(self) -> dict:
        """Returns the current grading metrics totals."""
        if not self.metrics_rows:
            return {
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'total_cost': 0.0,
                'call_count': 0
            }
        
        total_input = sum(r.get('input_tokens', 0) for r in self.metrics_rows)
        total_output = sum(r.get('output_tokens', 0) for r in self.metrics_rows)
        total_cost = sum(r.get('total_cost_usd', 0) for r in self.metrics_rows)
        
        return {
            'input_tokens': total_input,
            'output_tokens': total_output,
            'total_tokens': total_input + total_output,
            'total_cost': total_cost,
            'call_count': len(self.metrics_rows)
        }

    def print_combined_summary(self, answer_upload=None) -> None:
        """
        Print combined OCR + Grading metrics summary.
        Reads OCR metrics from database if answer_upload is provided (more reliable),
        otherwise falls back to in-memory collector.
        """
        grading = self.get_metrics_totals()
        
        # Try to get OCR metrics from database (more reliable since OCR runs in different task)
        ocr = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'total_cost': 0.0, 'call_count': 0}
        
        if answer_upload:
            try:
                from .models import AIMetrics
                from django.db.models import Sum
                
                ocr_metrics = AIMetrics.objects.filter(
                    answer_upload=answer_upload, 
                    process_type='OCR'
                ).aggregate(
                    total_input=Sum('input_tokens'),
                    total_output=Sum('output_tokens'),
                    total_tokens=Sum('total_tokens'),
                    total_cost=Sum('total_cost_usd')
                )
                
                ocr['input_tokens'] = ocr_metrics['total_input'] or 0
                ocr['output_tokens'] = ocr_metrics['total_output'] or 0
                ocr['total_tokens'] = ocr_metrics['total_tokens'] or 0
                ocr['total_cost'] = float(ocr_metrics['total_cost'] or 0)
                ocr['call_count'] = AIMetrics.objects.filter(
                    answer_upload=answer_upload, 
                    process_type='OCR'
                ).count()
                
                logger.info(f"???? Read OCR metrics from DB: {ocr['call_count']} records")
                
            except Exception as e:
                logger.warning(f"Failed to read OCR metrics from DB: {e}")
                # Fall back to in-memory collector
                from .ocr_processing_core import get_ocr_metrics_totals
                ocr = get_ocr_metrics_totals()
        else:
            # Fall back to in-memory collector (may be empty if OCR ran in different process)
            from .ocr_processing_core import get_ocr_metrics_totals
            ocr = get_ocr_metrics_totals()
        
        combined_input = ocr['input_tokens'] + grading['input_tokens']
        combined_output = ocr['output_tokens'] + grading['output_tokens']
        combined_tokens = ocr['total_tokens'] + grading['total_tokens']
        combined_cost = ocr['total_cost'] + grading['total_cost']
        
        logger.info("==== ???? COMBINED METRICS SUMMARY (OCR + GRADING) ====")
        logger.info(f"???? OCR:      Input: {ocr['input_tokens']:,} | Output: {ocr['output_tokens']:,} | Total: {ocr['total_tokens']:,} | Cost: ${ocr['total_cost']:.6f}")
        logger.info(f"???? Grading:  Input: {grading['input_tokens']:,} | Output: {grading['output_tokens']:,} | Total: {grading['total_tokens']:,} | Cost: ${grading['total_cost']:.6f}")
        logger.info(f"???? COMBINED: Input: {combined_input:,} | Output: {combined_output:,} | Total: {combined_tokens:,} | Cost: ${combined_cost:.6f}")
        logger.info("=====================================================")

    # ---------------------------
    # Existing grading & helper functions (Unchanged)
    # ---------------------------

    def load_answer_key(self, json_path: str) -> Tuple[Dict, Dict]:
        """
        Loads the answer key strictly from a JSON file.
        Returns: (answer_key_dict, diagram_paths_mapping)
        """
        try:
            logger.info(f"???? Loading Answer Key JSON from: {json_path}")
            
            with open(json_path, 'r', encoding='utf-8') as f:
                answer_key = json.load(f)
            
            # Map diagrams if they exist in the JSON
            # Expected JSON structure for diagrams: "reference_diagrams": ["path/to/image.png"]
            diagram_paths_mapping = {}
            
            for q_num, q_data in answer_key.items():
                # 1. Check top level diagrams
                if "reference_diagrams" in q_data:
                    diagram_paths_mapping[q_num] = q_data["reference_diagrams"]
                
                # 2. Check alternatives (if any)
                if "alternatives" in q_data:
                    for alt_key, alt_data in q_data["alternatives"].items():
                        if "reference_diagrams" in alt_data:
                            # Map to parent Q
                            if q_num not in diagram_paths_mapping:
                                diagram_paths_mapping[q_num] = []
                            # Add strictly unique paths
                            current_paths = set(diagram_paths_mapping[q_num])
                            for path in alt_data["reference_diagrams"]:
                                if path not in current_paths:
                                    diagram_paths_mapping[q_num].append(path)

            logger.info(f"??? Loaded Answer Key: {len(answer_key)} questions found.")
            
            # Store for the instance
            self.answer_key = answer_key
            self.answer_key_diagrams = diagram_paths_mapping
            
            return answer_key, diagram_paths_mapping

        except Exception as e:
            logger.error(f"??? CRITICAL: Failed to load answer key JSON: {e}", exc_info=True)
            raise ValueError(f"Invalid JSON Answer Key: {e}")

    def _merge_continuation_questions(self, student_answer: Dict) -> Dict:
        """
        Merges continuation questions (e.g., Q1_cont1) into their parent
        question (e.g., Q1).
        This version is robust against 'None' values in the JSON.
        """
        merged_answer = student_answer.copy() # Start with a copy to avoid mutation issues during iteration
        keys_to_remove = []

        # Get all keys that look like continuations
        continuation_keys = [k for k in merged_answer.keys() if "_cont" in k]
        
        # Sort them to ensure we merge cont1 before cont2, etc.
        continuation_keys.sort() 

        for cont_key in continuation_keys:
            # More flexible regex: matches Q1_cont1, Q1a_cont_2, etc.
            match = re.match(r"^(.*?)(?:_cont\d+)$", cont_key)
            if match:
                parent_key = match.group(1)
                
                if parent_key in merged_answer:
                     parent_data = merged_answer[parent_key]
                     cont_data = merged_answer[cont_key]

                     # --- MERGE LOGIC (WITH FIXES) ---
                     if "text" in cont_data:
                         parent_data["text"] = (parent_data.get("text", "") + "\n" + cont_data.get("text", "")).strip()
                     
                     # --- FIX FOR EQUATIONS ---
                     if "equations" in cont_data:
                         # Check if parent key is not a list (e.g., is None or missing)
                         if not isinstance(parent_data.get("equations"), list):
                             parent_data["equations"] = []
                         # Check if continuation data is a list
                         if isinstance(cont_data.get("equations"), list):
                             parent_data["equations"].extend(cont_data["equations"])
                     
                     # --- FIX FOR BULLETS ---
                     if "bullets" in cont_data:
                         if not isinstance(parent_data.get("bullets"), list):
                             parent_data["bullets"] = []
                         if isinstance(cont_data.get("bullets"), list):
                             parent_data["bullets"].extend(cont_data["bullets"])

                     # --- FIX FOR TABLES ---
                     if "tables" in cont_data:
                          if not isinstance(parent_data.get("tables"), list):
                              parent_data["tables"] = []
                          if isinstance(cont_data.get("tables"), list):
                              parent_data["tables"].extend(cont_data["tables"])
                     
                     if "diagram" in cont_data:
                          # This logic is for dicts, not lists, so it's different
                          if not isinstance(parent_data.get("diagram"), dict): 
                              parent_data["diagram"] = {}
                          if isinstance(cont_data.get("diagram"), dict):
                              start_idx = len(parent_data["diagram"]) + 1
                              for i, path in enumerate(cont_data["diagram"].values(), start=start_idx):
                                  parent_data["diagram"][str(i)] = path
                     # ------------------------------------
                     
                     logger.info(f"???? Merged {cont_key} into {parent_key}")
                     keys_to_remove.append(cont_key)
                else:
                     logger.warning(f"?????? Orphan continuation found: {cont_key} (Parent {parent_key} missing)")

        # Cleanup merged keys
        for k in keys_to_remove:
            del merged_answer[k]

        return merged_answer
    def separate_student_questions(self, student_answer: Dict) -> Dict[str, Dict]:
        """Separate student answer into individual questions (Handles 'Q1', '1', and '1a' formats)"""
        separated_questions = {}

        for key, value in student_answer.items():
            clean_key = key.strip()
            
            # --- MODIFICATION: Added a new regex to catch '1a', '3b', etc. ---
            match = re.match(r"^\d+[a-zA-Z]", clean_key, re.IGNORECASE)
            # --- END MODIFICATION ---

            if clean_key.isdigit():
                clean_key = f"Q{clean_key}"
            elif re.match(r"^\d+[.)]", clean_key):
                # Extract leading digits once to avoid backslash issues inside f-strings
                digit_match = re.match(r"^\d+", clean_key)
                if digit_match:
                    clean_key = f"Q{digit_match.group(0)}"
            # --- MODIFICATION: Check for the new regex match ---
            elif match:
                # This will turn '3a' into 'Q3a'
                clean_key = f"Q{clean_key}"
            # --- END MODIFICATION ---
            
            # Now, '3a' will be 'Q3a' and pass this check
            if clean_key.startswith("Q") or clean_key.lower().startswith("ans"):
                # Standardize "Ans1" -> "Q1" if needed, or keep as is
                final_key = clean_key
                
                if isinstance(value, dict):
                    separated_questions[final_key] = value
                    logger.info(f"???? Found student answer for {final_key} (was {key})")
                else:
                    # Handle non-dict answers (strings/lists)
                    separated_questions[final_key] = {"answer": value}
                    logger.info(f"???? Found simple student answer for {final_key} (was {key})")

        logger.info(
            f"???? Separated {len(separated_questions)} questions from student answer"
        )
        return separated_questions

    def separate_answer_key_questions(self) -> Dict[str, Dict]:
        """Separate answer key into individual questions - DYNAMIC"""
        separated_questions = {}

        for key, value in self.answer_key.items():
            if key.startswith("Q") and isinstance(value, dict):
                separated_questions[key] = value
                logger.info(f"???? Found answer key for {key}")

        logger.info(
            f"???? Separated {len(separated_questions)} questions from answer key"
        )
        return separated_questions

    def map_questions(
        self, student_questions: Dict, answer_key_questions: Dict
    ) -> Dict[str, Tuple[Dict, Dict]]:
        """Map student questions to answer key questions."""
        
        # --- NEW: Run the grouping logic first ---
        grouped_answer_key = self._group_answer_key_variants(answer_key_questions)
        # -----------------------------------------

        mapped_questions = {}

        for q_num in grouped_answer_key.keys():
            # 1. Try EXACT match first
            if q_num in student_questions:
                 mapped_questions[q_num] = (student_questions[q_num], grouped_answer_key[q_num])
                 logger.info(f"???? Mapped {q_num} (Exact)")
            else:
                # 2. Fuzzy match fallback
                fuzzy_matches = [sq for sq in student_questions if re.match(rf"^{q_num}[a-z._]", sq, re.IGNORECASE)]
                
                if fuzzy_matches:
                    student_match = fuzzy_matches[0]
                    mapped_questions[q_num] = (student_questions[student_match], grouped_answer_key[q_num])
                    logger.info(f"???? Mapped {q_num} (Fuzzy match to {student_match})")
                else:
                    # No match found
                    mapped_questions[q_num] = ({"answer": "No answer provided"}, grouped_answer_key[q_num])
                    logger.warning(f"?????? No student answer found for {q_num}")

        return mapped_questions

    def load_student_answer(self, json_file_path: str) -> Dict:
        """Load student answer from JSON file with error handling"""
        try:
            with open(json_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(
                f"Error loading student answer from {json_file_path}: {e}"
            )
            return {}

    def get_student_diagrams_by_question(
        self, student_answer: Dict, output_folder: Path
    ) -> Dict[str, List]:
        """Extract student diagrams organized by question number"""
        diagrams_by_question = {}

        for question_key, question_data in student_answer.items():
            if isinstance(question_data, dict) and "diagram" in question_data:
                
                diagram_data = question_data["diagram"]

                # Check if it's a dictionary
                if isinstance(diagram_data, dict):
                    diagrams_by_question[question_key] = []
                    
                    for diagram_key, diagram_path in diagram_data.items():
                        
                        # --- PATH FIX: Robustly find the file on disk ---
                        # 1. Clean the path (remove 'media/' if OCR put it there)
                        clean_path = str(diagram_path).replace("\\", "/")
                        if clean_path.startswith("media/"):
                            clean_path = clean_path.replace("media/", "", 1)
                        
                        # 2. Construct absolute path using Django settings
                        # This ensures D:/Lysa/grade_be/media/ + output/15/images/... works
                        full_path = Path(settings.MEDIA_ROOT) / clean_path
                        
                        # 3. Fallback: try output_folder if MEDIA_ROOT fails
                        if not full_path.exists():
                             full_path = output_folder / Path(clean_path).name

                        if full_path.exists():
                            try:
                                with Image.open(full_path) as img:
                                    image = img.copy()
                                diagrams_by_question[question_key].append(
                                    {
                                        "key": diagram_key,
                                        "image": image,
                                        "path": str(full_path),
                                    }
                                )
                                logger.info(
                                    f"??? Loaded student diagram for {question_key}: {full_path}"
                                )
                            except Exception as e:
                                logger.error(
                                    f"??? Error loading student diagram {full_path}: {e}"
                                )
                        else:
                            logger.warning(
                                f"??????  Student diagram file not found on disk: {full_path}"
                            )

        return diagrams_by_question

    def get_answer_key_diagrams_by_question(self) -> Dict[str, List]:
        """Get answer key diagrams organized by question number"""
        diagrams_by_question = {}

        for question_key, diagram_paths in self.answer_key_diagrams.items():
            diagrams_by_question[question_key] = []

            for diagram_path in diagram_paths:
                full_path = Path(diagram_path)
                
                # Check absolute first
                if not full_path.exists():
                     # Fallback 1: Try relative to MEDIA_ROOT
                     full_path = Path(settings.MEDIA_ROOT) / diagram_path
                
                if full_path.exists():
                    try:
                        # image = Image.open(full_path)
                        with Image.open(full_path) as img:
                            image = img.copy()
                        diagrams_by_question[question_key].append(
                            {"image": image, "path": str(full_path)}
                        )
                        logger.info(
                            f"??? Loaded reference diagram for {question_key}: {full_path}"
                        )
                    except Exception as e:
                        logger.error(
                            f"??? Error loading answer key diagram {full_path}: {e}"
                        )
                else:
                    logger.warning(f"?????? Reference diagram file not found: {diagram_path}")

        return diagrams_by_question

    def _parse_evaluation_criteria(self, criteria: List[str]) -> List[Dict]:
        """Parse evaluation criteria to extract marks allocation"""
        if not criteria:
            return []

        parsed_criteria = []

        for criterion in criteria:
            
            # --- THIS IS THE FIX ---
            # Changed the regex to match *only* a number in parentheses,
            # e.g., "(3)", "(2)", etc.
            marks_match = re.search(r"\((\d+)\)", criterion)
            # --- END FIX ---

            marks = int(marks_match.group(1)) if marks_match else 1

            clean_criterion = re.sub(
                r"\s*\(\d+\)", "", criterion
            ).strip()

            parsed_criteria.append(
                {"criterion": clean_criterion, "allocated_marks": marks}
            )

        return parsed_criteria

    def _create_deterministic_prompt_hash(self, student_answer: Dict) -> str:
        """Create deterministic hash for consistent grading"""
        answer_str = json.dumps(student_answer, sort_keys=True)
        return hashlib.md5(answer_str.encode()).hexdigest()[:8]
    
    def _group_answer_key_variants(self, answer_key_questions: Dict) -> Dict:
        """
        Detects split keys (e.g. Q3_A, Q3_B) and groups them into a single 
        logical question object with an 'alternatives' block.
        """
        grouped_keys = {}
        processed_keys = set()

        sorted_keys = sorted(answer_key_questions.keys())

        for key in sorted_keys:
            if key in processed_keys:
                continue

            # Regex to find Q3 from Q3_A, Q3_B, or Q3_Option_A
            # It looks for "Q" + digits, followed optionally by "_" + suffix
            match = re.match(r"^(Q\d+)(?:_(.+))?$", key)
            
            if match:
                base_key = match.group(1)  # e.g., Q3
                
                # Find all keys that start with "Q3_" or equal "Q3"
                related_keys = [
                    k for k in sorted_keys 
                    if k == base_key or k.startswith(base_key + "_")
                ]

                if len(related_keys) > 1:
                    logger.info(f"???? Grouping split keys for {base_key}: {related_keys}")
                    
                    # Create the synthetic parent object
                    synthesized_q = {
                        "type": "mixed",
                        "allocated_marks": 0,
                        "evaluation_criteria": [],
                        "criteria_status": "defined",
                        "is_either_or": True,
                        "alternatives": {}
                    }
                    
                    # Track base marks separately to add alternative marks later
                    base_marks = 0
                    alternative_marks_added = False

                    for sub_key in related_keys:
                        sub_data = answer_key_questions[sub_key]
                        
                        # If it is the base key (e.g. "Q3"), it holds common criteria
                        if sub_key == base_key:
                            base_marks = sub_data.get("allocated_marks", 0)
                            synthesized_q["evaluation_criteria"].extend(sub_data.get("evaluation_criteria", []))
                            # Copy other common fields if needed
                            if "expected_answer" in sub_data:
                                synthesized_q["expected_answer"] = sub_data["expected_answer"]
                        
                        # If it is a variant (e.g. "Q3_A")
                        else:
                            # Extract suffix (e.g. "A") to use as the option key
                            suffix = sub_key.replace(base_key + "_", "").lower() # "A" -> "a"
                            synthesized_q["alternatives"][f"option_{suffix}"] = sub_data
                            
                            # Add marks from the FIRST alternative only (either/or, so we pick one)
                            # Total = base common marks + one alternative's marks
                            if not alternative_marks_added:
                                synthesized_q["allocated_marks"] = base_marks + sub_data.get("allocated_marks", 0)
                                alternative_marks_added = True
                                logger.info(f"???? {base_key}: Base marks ({base_marks}) + Alternative marks ({sub_data.get('allocated_marks', 0)}) = {synthesized_q['allocated_marks']}")

                    grouped_keys[base_key] = synthesized_q
                    processed_keys.update(related_keys)
                else:
                    # Not a split question
                    grouped_keys[key] = answer_key_questions[key]
                    processed_keys.add(key)
            else:
                grouped_keys[key] = answer_key_questions[key]
                processed_keys.add(key)

        return grouped_keys
        
    def prepare_flexible_grading_prompt(
        self,
        question_num: str,
        question_data: Dict,
        student_answer: Dict,
        student_diagrams: Dict,
        answer_key_diagrams: Dict,
    ) -> str:
        """Prepare grading prompt that handles defined, undefined, and complex nested criteria."""

        evaluation_criteria = question_data.get("evaluation_criteria", [])
        
        # Handle Object-style evaluation_criteria (like in Q4/Q5)
        complex_criteria = {}
        if isinstance(evaluation_criteria, dict):
            complex_criteria = evaluation_criteria
            if "marking_scheme" in evaluation_criteria:
                evaluation_criteria = evaluation_criteria["marking_scheme"]
            else:
                evaluation_criteria = [] 
        
        criteria_status = question_data.get("criteria_status", "defined")
        parsed_criteria = (
            self._parse_evaluation_criteria(evaluation_criteria)
            if isinstance(evaluation_criteria, list) and evaluation_criteria
            else []
        )

        answer_hash = self._create_deterministic_prompt_hash(
            {question_num: student_answer}
        )

        # Build expected answer prompt
        expected_answer_obj = {}
        if question_data.get("expected_answer"):
            expected_answer_obj["text"] = question_data["expected_answer"]
        if question_data.get("expected_table"):
            expected_answer_obj["tables"] = [question_data["expected_table"]]
        if question_data.get("expected_label"):
            expected_answer_obj["bullets"] = question_data["expected_label"]
        
        # --- MODIFICATION: Load Alternatives Prompt from file ---
        alternatives_prompt = ""
        if "alternatives" in question_data:
            try:
                alt_template = load_prompt("grading_alternatives_snippet.txt")
                alternatives_prompt = alt_template.format(
                    alternatives_json=json.dumps(question_data['alternatives'], indent=2)
                )
            except Exception as e:
                logger.error(f"Failed to load grading_alternatives_snippet.txt: {e}")
                # Fallback (optional) or leave empty
                alternatives_prompt = ""

        # --- MODIFICATION: Load Diagram Criteria Prompt from file ---
        diagram_criteria_prompt = ""
        if "diagram_evaluation_criteria" in complex_criteria:
            try:
                diag_template = load_prompt("grading_diagram_criteria_snippet.txt")
                diagram_criteria_prompt = diag_template.format(
                    diagram_criteria_json=json.dumps(complex_criteria['diagram_evaluation_criteria'], indent=2)
                )
            except Exception as e:
                logger.error(f"Failed to load grading_diagram_criteria_snippet.txt: {e}")
                diagram_criteria_prompt = ""

        expected_answer_prompt = (
            json.dumps(expected_answer_obj)
            if expected_answer_obj
            else '"Refer to evaluation criteria/alternatives"'
        )
        
        # Load Base Template
        base_template = load_prompt("grading_base_prompt.txt")
        student_answer_json = json.dumps(student_answer, indent=2)

        base_prompt = base_template.format(
            answer_hash=answer_hash,
            question_num=question_num,
            question_type=question_data.get('type', 'mixed'),
            allocated_marks=question_data.get('allocated_marks', 0),
            student_answer_json=student_answer_json,
            expected_answer_prompt=expected_answer_prompt,
            alternatives_prompt=alternatives_prompt,
            diagram_criteria_prompt=diagram_criteria_prompt
        )

        # Append Instructions based on Criteria Status
        if criteria_status == "not_defined" and not parsed_criteria and not alternatives_prompt:
            instructions = load_prompt("grading_no_criteria_instructions.txt")
            prompt = f"{base_prompt}\n\n{instructions}"
        else:
            instructions_template = load_prompt("grading_with_criteria_instructions.txt")
            criteria_json = json.dumps(parsed_criteria, indent=2)
            instructions = instructions_template.format(criteria_json=criteria_json)
            prompt = f"{base_prompt}\n\n{instructions}"
        
        return prompt

    def _grade_batch(
        self,
        batch_questions: Dict,
        student_diagrams: Dict,
        answer_key_diagrams: Dict[str, List],
        batch_num: int,
        total_batches: int
    ) -> List[Dict]:
        """
        Grades a single batch of questions.
        Helper method for grade_student_batched.
        """
        logger.info(f"???? Processing Batch {batch_num}/{total_batches} with {len(batch_questions)} questions...")
        
        # 1. Prepare Data & Images for this batch
        task_data = []
        all_images = []
        image_mapping_text = ""
        image_counter = 0
        
        # Sort for deterministic order
        sorted_q_nums = sorted(batch_questions.keys(), key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 999)

        for q_num in sorted_q_nums:
            student_q, answer_key_q = batch_questions[q_num]
            
            # --- Handle Images ---
            q_images_refs = []
            
            # Student Images
            if q_num in student_diagrams:
                for diag in student_diagrams[q_num]:
                    all_images.append(diag["image"])
                    image_mapping_text += f"Image {image_counter}: Student Diagram for {q_num}\n"
                    q_images_refs.append(f"Image {image_counter} (Student)")
                    image_counter += 1
            
            # Reference Images
            if q_num in answer_key_diagrams:
                for diag in answer_key_diagrams[q_num]:
                    all_images.append(diag["image"])
                    image_mapping_text += f"Image {image_counter}: Reference Diagram for {q_num}\n"
                    q_images_refs.append(f"Image {image_counter} (Reference)")
                    image_counter += 1
            
            # --- Handle Complex Criteria (Text vs Diagram) ---
            raw_criteria = answer_key_q.get("evaluation_criteria", [])
            text_criteria = raw_criteria
            diagram_criteria = []

            # If criteria is a Dictionary (Complex Object from PDF)
            if isinstance(raw_criteria, dict):
                if "diagram_evaluation_criteria" in raw_criteria:
                    diagram_criteria = raw_criteria["diagram_evaluation_criteria"]
                
                if "marking_scheme" in raw_criteria:
                    text_criteria = raw_criteria["marking_scheme"]
                else:
                    text_criteria = [f"{k}: {v}" for k, v in raw_criteria.items() if k != "diagram_evaluation_criteria"]

            # Prepare Question Data Payload
            q_data = {
                "question_number": q_num,
                "allocated_marks": answer_key_q.get("allocated_marks", 0),
                "student_answer": student_q, 
                "evaluation_criteria": text_criteria,
                "diagram_evaluation_criteria": diagram_criteria,
                "expected_answer": answer_key_q.get("expected_answer", ""),
                "referenced_images": q_images_refs
            }
            
            # Handle Alternatives
            if "alternatives" in answer_key_q:
                q_data["alternatives"] = answer_key_q["alternatives"]
                
            task_data.append(q_data)

        # 2. Load and Format Prompt from File
        try:
            template = load_prompt("grading_single_call_prompt.txt")
            prompt_text = template.format(
                image_mapping_text=image_mapping_text,
                task_data_json=json.dumps(task_data, indent=2)
            )
        except Exception as e:
            logger.error(f"Failed to load grading prompt: {e}")
            raise

        contents = [prompt_text] + all_images
        
        # 3. Call API
        response = self.client.generate_structured_json(
            contents=contents,
            schema=GradingResultList.model_json_schema(),
            call_type_for_logging=f"grade_batch_{batch_num}"
        )
        
        # Log Metrics IMMEDIATELY after API call (before parsing)
        # This ensures we capture costs even if parsing fails
        self._log_metrics_for_question(
            question_num=f"BATCH_{batch_num}",
            prompt_text=prompt_text,
            student_answer_obj={"count": len(task_data)},
            expected_answer_prompt=None,
            response_text=response.response or "",
            num_student_images=len(all_images),
            num_reference_images=0,
            input_tokens=response.prompt_tokens,
            output_tokens=response.completion_tokens,
            actual_total_cost=response.cost
        )
        
        if response.error:
            logger.error(f"API Error in batch {batch_num} grading: {response.error}")
            raise Exception(f"API Error: {response.error}")
            
        # 4. Parse Result (metrics already logged above)
        try:
            result_list = GradingResultList.model_validate_json(response.response)
        except Exception as parse_error:
            # Track this as a wasted/failed call
            if response.cost and response.cost > 0:
                self.failed_call_metrics.append({
                    "batch_id": f"BATCH_{batch_num}",
                    "input_tokens": response.prompt_tokens or 0,
                    "output_tokens": response.completion_tokens or 0,
                    "total_cost": response.cost,
                    "error": str(parse_error)[:100]
                })
            logger.error(f"??? Parse failed for batch {batch_num} (tokens already logged): {parse_error}")
            raise
        
        logger.info(f"??? Batch {batch_num}/{total_batches} completed successfully")
        return [r.model_dump() for r in result_list.root]

    def grade_student_single_call(
        self,
        mapped_questions: Dict,
        student_diagrams: Dict,
        answer_key_diagrams: Dict[str, List],
        max_complexity_per_batch: int = 50
    ) -> List[Dict]:
        """
        Grades questions using ADAPTIVE BATCHING based on question complexity.
        Automatically retries failed batches by splitting them in half.
        
        Args:
            mapped_questions: Dict of question_num -> (student_answer, answer_key)
            student_diagrams: Dict of diagrams from student answers
            answer_key_diagrams: Dict of reference diagrams
            max_complexity_per_batch: Maximum complexity score allowed per batch (default: 50)
        
        Returns:
            List of grading result dictionaries
        """
        total_questions = len(mapped_questions)
        
        # Sort question numbers for deterministic ordering
        sorted_q_nums = sorted(
            mapped_questions.keys(), 
            key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 999
        )
        
        # Calculate complexity for each question
        question_complexities = {}
        for q_num in sorted_q_nums:
            student_q, answer_key_q = mapped_questions[q_num]
            complexity = self._calculate_question_complexity(
                student_q, 
                answer_key_q,
                student_diagrams.get(q_num, [])
            )
            question_complexities[q_num] = complexity
        
        # Create adaptive batches based on complexity
        batches = self._create_adaptive_batches(
            sorted_q_nums, 
            question_complexities, 
            mapped_questions,
            max_complexity_per_batch
        )
        
        # Log batch distribution
        batch_sizes = [len(b) for b in batches]
        batch_complexities = [
            sum(question_complexities[q] for q in b) for b in batches
        ]
        logger.info(f"???? Starting ADAPTIVE Batched Grading for {total_questions} questions...")
        logger.info(f"???? Created {len(batches)} adaptive batches:")
        for i, (size, complexity) in enumerate(zip(batch_sizes, batch_complexities), 1):
            logger.info(f"   Batch {i}: {size} questions, complexity={complexity}")
        
        # Process each batch with retry logic
        all_results = []
        for batch_idx, batch_q_nums in enumerate(batches, start=1):
            batch_questions = {q_num: mapped_questions[q_num] for q_num in batch_q_nums}
            
            results = self._grade_batch_with_retry(
                batch_questions=batch_questions,
                student_diagrams=student_diagrams,
                answer_key_diagrams=answer_key_diagrams,
                batch_num=batch_idx,
                total_batches=len(batches),
                depth=0
            )
            all_results.extend(results)
        
        logger.info(f"???? Adaptive batched grading complete. Processed {len(all_results)} questions total.")
        return all_results

    def _calculate_question_complexity(
        self, 
        student_answer: Dict, 
        answer_key: Dict,
        student_diagrams: List
    ) -> int:
        """
        Calculate complexity score for a question to enable adaptive batching.
        Higher scores indicate more complex questions that need smaller batches.
        """
        score = 0
        
        # 1. Student answer text length
        student_text = ""
        if isinstance(student_answer, dict):
            student_text = student_answer.get("text", "") or ""
            if isinstance(student_answer.get("bullets"), list):
                student_text += " ".join(student_answer.get("bullets", []))
            if isinstance(student_answer.get("equations"), list):
                for eq in student_answer.get("equations", []):
                    if isinstance(eq, dict):
                        student_text += eq.get("equation", "")
                    else:
                        student_text += str(eq)
        elif isinstance(student_answer, str):
            student_text = student_answer
        
        score += len(student_text) // 100  # +1 per 100 chars
        
        # 2. LaTeX/equation markers (chemistry formulas, math equations)
        latex_markers = student_text.count("\\") + student_text.count("$")
        score += latex_markers * 2
        
        # 3. Chemistry-specific patterns
        chemistry_patterns = [
            "kJ", "mol", "???", "???", "??", "??C", "pH", "M ", 
            "H2O", "CO2", "NaCl", "HCl", "NaOH"
        ]
        for pattern in chemistry_patterns:
            if pattern in student_text:
                score += 3
        
        # 4. Mark weight (higher marks = longer expected response)
        allocated_marks = answer_key.get("allocated_marks", 1)
        score += int(allocated_marks) * 2
        
        # 5. Diagrams (images are expensive)
        if student_diagrams:
            score += len(student_diagrams) * 10
        
        # 6. Reference diagrams from answer key
        ref_diagrams = answer_key.get("reference_diagram_paths", [])
        if ref_diagrams:
            score += len(ref_diagrams) * 5
        
        # Minimum score of 1
        return max(1, score)

    def _create_adaptive_batches(
        self,
        sorted_q_nums: List[str],
        question_complexities: Dict[str, int],
        mapped_questions: Dict,
        max_complexity: int
    ) -> List[List[str]]:
        """
        Create batches with adaptive sizing based on complexity budget.
        Each batch targets a maximum total complexity score.
        """
        batches = []
        current_batch = []
        current_complexity = 0
        
        for q_num in sorted_q_nums:
            q_complexity = question_complexities[q_num]
            
            # If adding this question exceeds budget AND we have questions in batch
            if current_complexity + q_complexity > max_complexity and current_batch:
                # Save current batch and start new one
                batches.append(current_batch)
                current_batch = [q_num]
                current_complexity = q_complexity
            else:
                # Add to current batch
                current_batch.append(q_num)
                current_complexity += q_complexity
        
        # Don't forget the last batch
        if current_batch:
            batches.append(current_batch)
        
        return batches

    def _grade_batch_with_retry(
        self,
        batch_questions: Dict,
        student_diagrams: Dict,
        answer_key_diagrams: Dict[str, List],
        batch_num: int,
        total_batches: int,
        depth: int = 0
    ) -> List[Dict]:
        """
        Grade a batch with automatic retry-with-split on failure.
        If a batch fails, it splits in half and retries each half.
        """
        max_depth = 5  # Prevent infinite recursion
        
        try:
            logger.info(f"???? Processing Batch {batch_num}/{total_batches} with {len(batch_questions)} questions (depth={depth})...")
            
            batch_results = self._grade_batch(
                batch_questions=batch_questions,
                student_diagrams=student_diagrams,
                answer_key_diagrams=answer_key_diagrams,
                batch_num=batch_num,
                total_batches=total_batches
            )
            return batch_results
            
        except Exception as e:
            logger.error(f"??? Batch {batch_num} failed (depth={depth}): {e}")
            
            # Can we split further?
            if len(batch_questions) > 1 and depth < max_depth:
                logger.info(f"???? Splitting batch {batch_num} into 2 smaller batches and retrying...")
                
                q_nums = list(batch_questions.keys())
                mid = len(q_nums) // 2
                
                left_q_nums = q_nums[:mid]
                right_q_nums = q_nums[mid:]
                
                left_batch = {q: batch_questions[q] for q in left_q_nums}
                right_batch = {q: batch_questions[q] for q in right_q_nums}
                
                # Recursively retry each half
                left_results = self._grade_batch_with_retry(
                    batch_questions=left_batch,
                    student_diagrams=student_diagrams,
                    answer_key_diagrams=answer_key_diagrams,
                    batch_num=batch_num,
                    total_batches=total_batches,
                    depth=depth + 1
                )
                
                right_results = self._grade_batch_with_retry(
                    batch_questions=right_batch,
                    student_diagrams=student_diagrams,
                    answer_key_diagrams=answer_key_diagrams,
                    batch_num=batch_num,
                    total_batches=total_batches,
                    depth=depth + 1
                )
                
                return left_results + right_results
            else:
                # Can't split further - create error results
                logger.error(f"??? Cannot split further. Creating error results for {len(batch_questions)} questions.")
                error_results = []
                for q_num, (_, answer_key_q) in batch_questions.items():
                    error_results.append(
                        self._create_error_question_result(q_num, answer_key_q, str(e))
                    )
                return error_results


                
    def analyze_concepts_for_question(self, question_num: str, question_data: Dict, student_answer: Dict, grading_feedback: str) -> Dict:
        """
        Runs a separate analysis to identify strong/weak concepts and confidence score.
        Delegates to the batch method for consistency with the prompt structure.
        """
        try:
            # Wrap as a single batch item
            batch_item = {
                "question_num": question_num,
                "question_data": question_data,
                "student_answer": student_answer,
                "grading_feedback": grading_feedback
            }
            
            # Use the batch method
            batch_results = self.analyze_concepts_for_batch([batch_item])
            
            if batch_results:
                return batch_results[0]
            return {}
            
        except Exception as e:
            logger.error(f"Concept Analysis failed for {question_num}: {e}")
            return {}

    def analyze_concepts_for_batch(self, batch_data: List[Dict]) -> List[Dict]:
        """
        Runs concept analysis for a batch of questions in a single API call.
        """
        if not batch_data:
            return []

        try:
            # Load prompt
            template = load_prompt("concept_analysis_prompt.yaml")
            
            questions_input_list = []
            for item in batch_data:
                q_data = item['question_data']
                student_answer = item['student_answer']
                
                answer_key_text = ""
                if q_data.get("evaluation_criteria"):
                     answer_key_text += f"Criteria: {json.dumps(q_data['evaluation_criteria'], indent=2)}\n"
                if q_data.get("expected_answer"):
                     answer_key_text += f"Expected Answer: {q_data['expected_answer']}\n"
                if q_data.get("alternatives"):
                     answer_key_text += f"Alternatives: {json.dumps(q_data['alternatives'], indent=2)}\n"

                questions_input_list.append({
                    "Question Number": item['question_num'],
                    "Question Type": q_data.get('type', 'mixed'),
                    "Allocated Marks": q_data.get('allocated_marks', 0),
                    "Answer Key / Evaluation Criteria": answer_key_text,
                    "Student's Answer": student_answer,
                    "Grading Feedback": item['grading_feedback']
                })
            
            input_json_str = json.dumps(questions_input_list, indent=2)
            final_prompt = f"{template}\n\nINPUT DATA LIST:\n{input_json_str}"
            
            # Call API
            response = self.client.generate_structured_json(
                contents=final_prompt,
                schema=ConceptAnalysisBatchResult.model_json_schema(),
                call_type_for_logging=f"concept_analysis_batch_{len(batch_data)}"
            )
            
            self._log_metrics_for_question(
                question_num=f"BATCH_CONCEPT_{len(batch_data)}",
                prompt_text=final_prompt,
                student_answer_obj={"batch_size": len(batch_data)},
                expected_answer_prompt=None,
                response_text=response.response or "",
                num_student_images=0,
                num_reference_images=0,
                input_tokens=response.prompt_tokens,
                output_tokens=response.completion_tokens,
                actual_total_cost=response.cost
            )
            
            if response.error:
                logger.error(f"Batch Concept Analysis API Error: {response.error}")
                return []
                
            batch_result_obj = ConceptAnalysisBatchResult.model_validate_json(response.response)
            return [res.model_dump() for res in batch_result_obj.results]
            
        except Exception as e:
            logger.error(f"Batch Concept Analysis failed: {e}")
            return []

    def grade_student(
        self, student_answer: Dict, output_folder: Path, student_id: str
    ) -> Dict:
        """Grade student answer using the robust question mapping approach"""
        try:
            # --- Pre-process to merge continuations ---
            student_answer = self._merge_continuation_questions(student_answer)

            # Step 1: Separate student questions
            student_questions = self.separate_student_questions(student_answer)

            # Step 2: Separate answer key questions
            answer_key_questions = self.separate_answer_key_questions()

            # Step 3: Map questions
            mapped_questions = self.map_questions(student_questions, answer_key_questions)

            # Step 4: Load Diagrams
            student_diagrams = self.get_student_diagrams_by_question(
                student_answer, output_folder
            )
            answer_key_diagrams = self.get_answer_key_diagrams_by_question()

            # Step 5: Perform Grading (Using Single Call Optimization)
            # This returns a list of result dictionaries directly
            raw_results = self.grade_student_single_call(
                mapped_questions, student_diagrams, answer_key_diagrams
            )

            # Step 6: Process and Validate Results
            processed_results = []
            batch_concept_input = []
            total_score = 0.0
            max_possible_score = 0.0

            for res in raw_results:
                q_num = res.get("question_number")
                
                # Retrieve original question data for validation
                if q_num in mapped_questions:
                    original_student_data, key_data = mapped_questions[q_num]
                    
                    # --- CRITICAL FIX: Overwrite student_answer with original data ---
                    res["student_answer"] = original_student_data
                    # -----------------------------------------------------------------
                    
                else:
                    # Fallback lookup (unlikely if API behaves)
                    key_data = answer_key_questions.get(q_num, {})

                # Validate marks caps and formatting
                validated_res = self._validate_question_result(res, key_data)
                
                # --- Prepare Batch Concept Analysis ---
                # Retrieve original student answer again (safe access)
                orig_student_ans = mapped_questions.get(q_num, ({}, {}))[0]
                grading_feedback_text = validated_res.get("summary") or validated_res.get("general_feedback") or ""
                
                batch_concept_input.append({
                    "question_num": q_num,
                    "question_data": key_data,
                    "student_answer": orig_student_ans,
                    "grading_feedback": grading_feedback_text
                })
                # --------------------------------------
                
                processed_results.append(validated_res)
                total_score += validated_res.get("obtained_marks", 0)
                max_possible_score += validated_res.get("allocated_marks", 0)

            # --- Execute Batch Concept Analysis ---
            if batch_concept_input:
                logger.info(f"???? Running Batch Concept Analysis for {len(batch_concept_input)} questions...")
                batch_concepts = self.analyze_concepts_for_batch(batch_concept_input)
                
                # Map back to results
                res_map = {r["question_number"]: r for r in processed_results}
                
                for concept_res in batch_concepts:
                    q_num = concept_res.get("question_number")
                    if q_num and q_num in res_map:
                        res_map[q_num]["concept_analysis"] = concept_res.get("concepts", [])
                        res_map[q_num]["confidence_percentage"] = concept_res.get("overall_confidence_percentage")
                        res_map[q_num]["confidence_level"] = concept_res.get("overall_confidence_level")
                        logger.info(f"??? Concept Analysis mapped for {q_num}")
            # --------------------------------------

            # Step 7: Construct Final Result
            final_result = {
                "total_score": total_score,
                "max_possible_score": max_possible_score,
                "results": processed_results,
                "student_id": student_id,
                "grading_metadata": {
                    "grading_method": "single_call_gemini_2.5",
                    "total_questions": len(mapped_questions),
                    "student_diagrams_count": sum(
                        len(d) for d in student_diagrams.values()
                    ),
                    "reference_diagrams_count": sum(
                        len(d) for d in answer_key_diagrams.values()
                    ),
                    "questions_with_diagrams": list(student_diagrams.keys()),
                    "reference_questions_with_diagrams": list(answer_key_diagrams.keys()),
                },
            }

            # --- NEW: Save Metrics to DB ---
            if self.answer_upload:
                self.save_metrics_to_db(self.answer_upload)

            return final_result

        except Exception as e:
            logger.error(f"Error during overall grading for {student_id}: {e}", exc_info=True)
            return self._create_error_result(student_id, str(e))

    def _validate_question_result(
        self, result: Dict, question_data: Dict
    ) -> Dict:
        """
        Validate question result and correctly populate the
        full 'expected_answer' object.
        """
        allocated = question_data.get("allocated_marks", 0)

        try:
            obtained = float(result.get("obtained_marks", 0))
        except (ValueError, TypeError):
            logger.warning(
                f"Invalid 'obtained_marks' value: {result.get('obtained_marks')}. Defaulting to 0."
            )
            obtained = 0
            
        # Ensure result has the float value
        result["obtained_marks"] = obtained

        # --- 1. Mark Capping and Clamping ---
        if obtained > allocated:
            logger.warning(
                f"Obtained marks ({obtained}) > Allocated marks ({allocated}). Capping to {allocated}."
            )
            result["obtained_marks"] = allocated
            if result.get("summary"):
                result["summary"] += f" [Note: Marks capped at maximum {allocated}]"

        if obtained < 0:
            result["obtained_marks"] = 0

        # --- 2. Criteria Consistency Check ---
        if result.get("criteria_breakdown"):
            criteria_total = sum(
                c.get("obtained_marks", 0)
                for c in result["criteria_breakdown"]
            )
            if abs(criteria_total - result["obtained_marks"]) > 0.1:
                logger.warning(
                    f"Criteria breakdown total ({criteria_total}) doesn't match obtained marks ({result['obtained_marks']}). Keeping total obtained."
                )

        # --- 3. Feedback Standardization ---
        primary_feedback = ""
        if result.get("summary"):
            primary_feedback = result["summary"]
        elif result.get("general_feedback"):
            primary_feedback = result["general_feedback"]
            
        result["final_feedback"] = (
            primary_feedback
            if primary_feedback
            else "No detailed feedback was generated by the AI."
        )

        # --- 4. Final Data Standardization ---
        result["allocated_marks"] = allocated
        result["question_type"] = question_data.get("type", "mixed")

        # --- NEW: Build the rich expected_answer object ---
        # This is the main fix
        new_expected_answer = {}
        
        # Check for alternatives first
        if "alternatives" in question_data:
            # We will show the expected answer for BOTH options
            # This is safer than trying to guess which one the AI picked
            new_expected_answer["text"] = "This was an 'EITHER/OR' question. See options below:"
            new_expected_answer["bullets"] = []
            
            for key, alt_data in question_data["alternatives"].items():
                alt_text = alt_data.get("expected_answer", f"Details for {key}")
                new_expected_answer["bullets"].append(f"Option ({key}): {alt_text}")

        # If not alternatives, use the top-level data
        else:
            if question_data.get("expected_answer"):
                new_expected_answer["text"] = question_data["expected_answer"]
            if question_data.get("expected_table"):
                new_expected_answer["tables"] = [question_data["expected_table"]]
            if question_data.get("expected_label"):
                new_expected_answer["bullets"] = question_data["expected_label"]

        # Add reference diagram paths (this works for both cases)
        if question_data.get("reference_diagrams"):
            diagram_dict = {}
            ref_diagrams = question_data["reference_diagrams"]
            
            if isinstance(ref_diagrams, list):
                for i, path_str in enumerate(ref_diagrams):
                    diagram_dict[str(i + 1)] = path_str
            elif isinstance(ref_diagrams, dict):
                diagram_dict = ref_diagrams

            if diagram_dict:
                new_expected_answer["diagram"] = diagram_dict

        result["expected_answer"] = new_expected_answer
        # --- END OF NEW LOGIC ---

        return result

    def _create_error_question_result(
        self, question_num: str, question_data: Dict, error_msg: str
    ) -> Dict:
        """Create error result for a single question"""
        return {
            "question_number": question_num,
            "question_type": question_data.get("type", "mixed"),
            "allocated_marks": question_data.get("allocated_marks", 0),
            "obtained_marks": 0,
            "student_answer": "Error loading answer",
            "expected_answer": question_data.get(
                "expected_answer", "No expected answer provided"
            ),
            "diagram_comparison": None,
            "evaluation_criteria_status": "error",
            "general_feedback": f"Grading failed: {error_msg} - Manual review required",
            "mistakes_identified": ["Grading system error"],
            "summary": f"Grading failed: {error_msg} - Manual review required",
            "final_feedback": f"Grading failed: {error_msg} - Manual review required",  # Ensure error results also have this key
        }

    def _create_error_result(self, student_id: str, error_msg: str) -> Dict:
        """Create error result when grading fails"""
        results = []
        total_allocated = 0

        for question_num, answer_data in self.answer_key.items():
            allocated = answer_data.get("allocated_marks", 0)
            total_allocated += allocated

            results.append(
                self._create_error_question_result(
                    question_num, answer_data, error_msg
                )
            )

        return {
            "total_score": 0,
            "max_possible_score": total_allocated,
            "results": results,
            "student_id": student_id,
            "error": error_msg,
            "grading_metadata": {
                "grading_method": "multi_pass_enhanced_extraction",
                "student_diagrams_count": 0,
                "reference_diagrams_count": 0,
                "questions_with_diagrams": [],
                "reference_questions_with_diagrams": [],
            },
        }

    def save_individual_result(
        self, result: Dict, results_folder: Path, student_id: str
    ) -> None:
        """Save individual student result"""
        results_folder.mkdir(exist_ok=True)
        result_file = results_folder / f"{student_id}_result.json"

        try:
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            logger.info(f"??? Result saved for {student_id}: {result_file}")
        except Exception as e:
            logger.error(f"??? Error saving result for {student_id}: {e}")

    def grade_all_students(
        self,
        output_folder: str,
        results_folder: str,
        answer_key_path: str, # This must now be a JSON path
        external_assets: Dict[str, str] = None,
    ) -> Dict[str, Any]:
        """
        Grades all student folders in the output directory using a JSON answer key.
        """
        # Ensure output folder exists
        if not os.path.exists(output_folder):
            raise FileNotFoundError(f"Output folder not found: {output_folder}")

        # 1. Load Answer Key (Strictly JSON)
        if not str(answer_key_path).lower().endswith('.json'):
             raise ValueError(f"??? Error: Answer key must be a .json file. Got: {answer_key_path}")

        self.answer_key, self.answer_key_diagrams = self.load_answer_key(answer_key_path)
        
        # --- Merge External Assets into Answer Key ---
        if external_assets:
            logger.info(f"Merging {len(external_assets)} external assets into Answer Key...")
            for asset_key, asset_path in external_assets.items():
                target_key = None
                
                # 1. Direct Match
                if asset_key in self.answer_key:
                    target_key = asset_key
                
                # 2. Try normalizing "Q4" -> "4" or "4" -> "Q4"
                if not target_key:
                    asset_num = "".join(filter(str.isdigit, asset_key))
                    if asset_num:
                        for ak_key in self.answer_key.keys():
                            ak_num = "".join(filter(str.isdigit, ak_key))
                            if asset_num == ak_num:
                                target_key = ak_key
                                break

                if target_key:
                    # Update Metadata
                    if "reference_diagrams" not in self.answer_key[target_key]:
                         self.answer_key[target_key]["reference_diagrams"] = []
                    
                    if asset_path not in self.answer_key[target_key]["reference_diagrams"]:
                        self.answer_key[target_key]["reference_diagrams"].append(asset_path)

                    # Update Loader Dict
                    if target_key not in self.answer_key_diagrams:
                        self.answer_key_diagrams[target_key] = []
                    
                    if asset_path not in self.answer_key_diagrams[target_key]:
                        self.answer_key_diagrams[target_key].append(asset_path)

                    logger.info(f"???? Injected asset {asset_key} into Question {target_key}")
        # --- END MERGE ---

        # ... (Rest of the function remains exactly the same as previous logic) ...
        # DEBUG: Show what was extracted
        logger.info(f"???? QUESTIONS LOADED: {list(self.answer_key.keys())}")
        
        # Setup paths
        output_path = Path(output_folder)
        results_path = Path(results_folder)

        # Find all JSON files
        json_files = list(output_path.glob("*.json"))

        if not json_files:
            logger.warning("??????  No JSON files found in output folder")
            return {"total_students": 0, "processed": 0, "errors": 0}

        logger.info(f"???? Found {len(json_files)} student files to grade")

        # Grade each student
        processed = 0
        errors = 0

        for json_file in json_files:
            try:
                student_id = json_file.stem
                logger.info(f"???? Grading student: {student_id}")

                student_answer = self.load_student_answer(json_file)

                if not student_answer:
                    logger.error(f"??? Failed to load answer for {student_id}")
                    errors += 1
                    continue

                result = self.grade_student(
                    student_answer, output_path, student_id
                )

                self.save_individual_result(result, results_path, student_id)

                if "error" not in result:
                    processed += 1
                else:
                    errors += 1

            except Exception as e:
                logger.error(f"??? Error processing {json_file}: {e}")
                errors += 1

        summary = {
            "total_students": len(json_files),
            "processed": processed,
            "errors": errors,
            "results_folder": str(results_path),
            "answer_key_questions": len(self.answer_key),
            "grading_method": "json_direct",
        }

        # Save metrics
        try:
            metrics_csv_path = results_path / f"grading_metrics_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
            self.save_metrics_csv(str(metrics_csv_path))
            self.print_metrics_summary()
            self.print_combined_summary(answer_upload=self.answer_upload)
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")

        return summary
