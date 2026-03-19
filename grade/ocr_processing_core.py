# ocr_processor.py
import os
import io
import re
import base64
import json
from collections import defaultdict
from PIL import Image
import fitz  # PyMuPDF
import cv2
import numpy as np
from ultralytics import YOLO
from dotenv import load_dotenv
import google.genai as genai
from google.genai.types import Part, Blob # <-- THIS IMPORT IS CORRECT
import time
from pydantic import BaseModel, Field, RootModel, ConfigDict
from typing import List, Dict, Optional, Any, Tuple
import logging
from django.conf import settings
from pathlib import Path
from centralised_llm.src.llms.gemini_genai_llm import GeminiGradingClient, GenerateResponse
from .models import AnswerUpload


# --- NEW IMPORTS FOR METRICS ---
import csv
import math
from datetime import datetime, timezone
# --- END NEW IMPORTS ---
logger = logging.getLogger(__name__)
# --- NEW: Centralized Client Instance ---
try:
    # We use "gemini-1.5-flash" here, but your client can be configured
    GRADING_CLIENT_INSTANCE = GeminiGradingClient(model_name="gemini-3-flash-preview")
    logger.info("[OK] Gemini Grading Client initialized.")
except ValueError as e:
    logger.critical(f"[ERROR] FAILED TO INITIALIZE GEMINI CLIENT: {e}")
    GRADING_CLIENT_INSTANCE = None
# --- END NEW CLIENT ---
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
                    logger.info(f"[OK] Loaded prompt from YAML: {yaml_filename}")
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
                logger.info(f"[FILE] Loaded prompt from TXT (fallback): {filename}")
                return f.read()
        except Exception as e:
            logger.error(f"Error reading TXT {txt_path}: {e}")
            raise
    
    # Neither file exists
    logger.error(f"CRITICAL: Prompt file not found: {yaml_path} or {txt_path}")
    raise FileNotFoundError(f"Missing prompt file: {yaml_filename} or {filename}")
# --- END PROMPT LOADER --- 

# --- NEW METRICS (Part 1): Classes and Global Instances ---

# Default prices per 1M tokens (override with env)
DEFAULT_INPUT_PRICE_PER_1M = float(os.getenv("GEMINI_INPUT_PRICE_PER_1M", "0.30"))
DEFAULT_OUTPUT_PRICE_PER_1M = float(
    os.getenv("GEMINI_OUTPUT_PRICE_PER_1M", "2.50")
)


class TokenCostCalculator:
    """Helper class to calculate token costs."""

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


class OCRMetricsCollector:
    """Collects per-OCR-call metrics and can save to CSV and print summaries."""
    
    # Standard fields for CSV - ensures all rows have consistent keys
    STANDARD_FIELDS = [
        "utc_ts", "call_type", "input_tokens", "output_tokens", 
        "total_tokens", "total_cost_usd"
    ]

    def __init__(self, cost_calc: TokenCostCalculator):
        self.rows: List[Dict[str, Any]] = []
        self.cost_calc = cost_calc

    def add_row(self, row: Dict[str, Any]):
        """Add a row with normalized fields to ensure CSV compatibility."""
        # Normalize row to have all standard fields with sensible defaults
        normalized_row = {}
        for field in self.STANDARD_FIELDS:
            if field in row:
                normalized_row[field] = row[field]
            elif 'tokens' in field:
                normalized_row[field] = 0
            elif 'cost' in field:
                normalized_row[field] = 0.0
            elif field == 'call_type':
                normalized_row[field] = 'unknown'
            else:
                normalized_row[field] = ''
        self.rows.append(normalized_row)

    def clear(self):
        """Clear collected metrics to prevent data leaking between tasks."""
        self.rows = []

    def save_csv(self, csv_path: Optional[str] = None):
        if not self.rows:
            logger.info("No OCR metrics to save.")
            return
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = Path(csv_path) if csv_path else Path(f"ocr_metrics_{ts}.csv")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.STANDARD_FIELDS)
                writer.writeheader()
                for r in self.rows:
                    writer.writerow(r)
            logger.info(f"Saved OCR metrics CSV to {out_path}")
        except Exception as e:
            logger.error(f"Failed to write metrics CSV: {e}")
        # We do NOT clear automatically here to allow printing summary later

    def print_summary(self):
        if not self.rows:
            logger.info("No OCR metrics to show.")
            return
            
        # FIX: Explicitly sum the total_tokens field from each row 
        # instead of recalculating from input/output
        total_input = sum(r.get("input_tokens", 0) for r in self.rows)
        total_output = sum(r.get("output_tokens", 0) for r in self.rows)
        total_tokens_sum = sum(r.get("total_tokens", 0) for r in self.rows)
        total_cost = sum(r.get("total_cost_usd", 0.0) for r in self.rows)
        
        n = len(self.rows)
        input_list = [r.get("input_tokens", 0) for r in self.rows]
        output_list = [r.get("output_tokens", 0) for r in self.rows]

        def pctile(data, p):
            if not data:
                return 0
            data_sorted = sorted(data)
            idx = max(
                0,
                min(
                    len(data_sorted) - 1,
                    math.ceil(len(data_sorted) * p / 100) - 1,
                ),
            )
            return data_sorted[idx]

        logger.info("==== OCR METRICS SUMMARY ====")
        logger.info(f"Calls captured: {n}")
        logger.info(f"Total input tokens: {total_input:,}")
        logger.info(f"Total output tokens: {total_output:,}")
        logger.info(f"Actual Total Tokens: {total_tokens_sum:,}")
        logger.info(f"Estimated total cost (USD): ${total_cost:.6f}")
        logger.info(f"Avg input tokens/call: {sum(input_list)/n:.1f}")
        logger.info(f"Avg output tokens/call: {sum(output_list)/n:.1f}")
        logger.info(
            f"P50 input: {pctile(input_list, 50):,}, P90 input: {pctile(input_list, 90):,}, P99 input: {pctile(input_list, 99):,}"
        )
        logger.info(
            f"P50 output: {pctile(output_list, 50):,}, P90 output: {pctile(output_list, 90):,}, P99 output: {pctile(output_list, 99):,}"
        )
        logger.info("============================")


# Create global instances for metrics collection
OCR_COST_CALCULATOR = TokenCostCalculator()
OCR_METRICS_COLLECTOR = OCRMetricsCollector(OCR_COST_CALCULATOR)
# --- END NEW METRICS (Part 1) ---
# --- Eager Load & Pre-warm YOLO Model ---
YOLO_MODEL_PATH = "grade/yolo/best2.pt"
YOLO_MODEL = None
if os.path.exists(YOLO_MODEL_PATH):
    try:
        logger.info("--- Loading YOLO Model... ---")
        YOLO_MODEL = YOLO(YOLO_MODEL_PATH)
        logger.info("--- YOLO Model instantiated. Pre-warming model... ---")

        # --- PRE-WARM FIX ---
        dummy_image = np.zeros((640, 640, 3), dtype=np.uint8)
        YOLO_MODEL.predict(source=dummy_image, verbose=False)
        logger.info("--- YOLO Model is now 'warm' and ready. ---")
        # --- END PRE-WARM FIX ---

    except Exception as e:
        logger.error(
            f"--- WARNING: Failed to load or pre-warm YOLO model: {e} ---"
        )
else:
    logger.warning(
        f"--- WARNING: YOLO model not found at {YOLO_MODEL_PATH}. Diagram detection will be skipped. ---"
    )
# --- END Eager Load ---


def get_json_extraction_prompt(output_path: str, user_id: int) -> List[Dict[str, str]]:
    # This function is no longer called by the new gemini_json_from_pdf,
    # but we leave it in case other parts of the system use it.
    
    # --- MODIFICATION: Load from file ---
    try:
        template_text = load_prompt("ocr_extraction_prompt.txt")
        prompt_text = template_text.format(output_path=output_path, user_id=user_id)
        return [{"text": prompt_text}]
    except Exception as e:
        logger.error(f"Failed to load ocr_extraction_prompt.txt: {e}")
        # Fallback to empty or error
        return [{"text": "Error: Could not load prompt."}]
    # --- END MODIFICATION ---


# --- Pydantic Schemas ---

class PageNumberResult(BaseModel):
    """Schema for extracting just a page number."""
    page_number: Optional[int] = Field(default=None, description="The extracted page number as an integer, or null if not found.")

class DiagramScanResult(BaseModel):
    """Schema for checking if a diagram exists."""
    has_diagram: bool = Field(description="True if one or more visual diagrams are present, False otherwise.")

class DiagramSelectionResult(RootModel[Dict[str, List[int]]]):
    """
    Schema for mapping question numbers to a list of box IDs.
    Example: {"Q3": [1, 4], "Q4": [2, 5]}
    """
    root: Dict[str, List[int]]

# Pydantic Models for validation (Your existing, correct models)
class EquationStep(BaseModel):
    step: int
    equation: str

# --- UPDATED SCHEMAS ---
class PageScanResult(BaseModel):
    """Schema for a single page's details."""
    page_index: int = Field(description="The 0-based index of the image in the provided list.")
    page_number: int = Field(default=9999, description="The handwritten page number, or 9999 if not found.")
    has_diagram: bool = Field(default=False, description="True if a visual diagram/drawing is present.")

class PageScanBatchResult(BaseModel):
    """Schema for the batch result of all pages."""
    results: List[PageScanResult]

class QuestionContent(BaseModel):
    text: Optional[str] = None
    equations: Optional[List[EquationStep]] = None
    tables: Optional[List[Dict[str, Any]]] = None
    bullets: Optional[List[str]] = None
    diagram: Optional[Dict[str, str]] = None


class OutputModel(RootModel[Dict[str, QuestionContent]]):
    pass
# --- END Pydantic Schemas ---


def crop_top_right(img: Image.Image) -> Image.Image:
    """Extract top-right corner for roll number/page number detection"""
    width, height = img.size
    return img.crop((width // 2, 0, width, height // 5))


# def scan_page_details(img: Image.Image) -> PageScanResult:
#     """
#     Scans a single page image to get BOTH the page number
#     and whether a diagram is present in one API call.
#     """
#     if not GRADING_CLIENT_INSTANCE:
#         logger.error("Gemini client not initialized. Cannot scan page details.")
#         return PageScanResult() # Return default values

#     prompt_text = load_prompt("scan_page_details_prompt.txt")
#     prompt_contents = [img, prompt_text]
    
#     try:
#         response = GRADING_CLIENT_INSTANCE.generate_structured_json(
#             contents=prompt_contents,
#             schema=PageScanResult.model_json_schema(),
#             call_type_for_logging="scan_page_details"
#         )
        
#         if response.error:
#             logger.error(f"Failed to scan page details: {response.error}")
#             return PageScanResult() # Return default values
        
#         # --- FIX: ADD METRICS COLLECTION ---
#         try:
#             input_tokens = GRADING_CLIENT_INSTANCE.client.models.count_tokens(
#                 model=GRADING_CLIENT_INSTANCE.model_name,
#                 contents=prompt_contents
#             ).total_tokens
            
#             row = {
#                 "utc_ts": datetime.utcnow().isoformat(),
#                 "call_type": "scan_page_details",
#                 "input_tokens": input_tokens,
#                 "output_tokens": response.completion_tokens,
#                 "total_tokens": input_tokens + response.completion_tokens,
#                 "input_cost_usd": "N/A",
#                 "output_cost_usd": "N/A",
#                 "total_cost_usd": response.cost,
#                 "response_length_chars": len(response.response),
#             }
#             OCR_METRICS_COLLECTOR.add_row(row)
#         except Exception as e:
#             logger.warning(f"Failed to add OCR metrics for scan_page_details: {e}")
#         # --- END FIX ---

#         result = PageScanResult.model_validate_json(response.response)
#         logger.info(f"  Page scan result -> Page: {result.page_number}, Diagram: {result.has_diagram}")
#         return result
        
#     except Exception as e:
#         logger.error(f"Failed to scan page details: {e}")
#         return PageScanResult() # Return default values

def smart_crop_content(pil_image: Image.Image, padding: int = 50) -> Image.Image:
    """
    Reduces vision tokens by cropping the image to the actual content (text/drawings),
    removing empty whitespace/margins.
    """
    try:
        # Convert PIL to OpenCV
        img_array = np.array(pil_image.convert('RGB'))
        # Convert RGB to BGR
        img_cv = img_array[:, :, ::-1].copy() 
        
        # Grayscale & Blur
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (25, 25), 0)
        
        # Threshold (Assume dark text on light background)
        _, thresh = cv2.threshold(blur, 240, 255, cv2.THRESH_BINARY_INV)
        
        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return pil_image # Return original if no content found

        # Find bounding box of all contours
        x_min, y_min = float('inf'), float('inf')
        x_max, y_max = float('-inf'), float('-inf')

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            # Filter noise (very small dots)
            if w * h > 500: 
                x_min = min(x_min, x)
                y_min = min(y_min, y)
                x_max = max(x_max, x + w)
                y_max = max(y_max, y + h)

        if x_min == float('inf'):
            return pil_image

        # Add padding
        h, w, _ = img_cv.shape
        x1 = max(0, int(x_min - padding))
        y1 = max(0, int(y_min - padding))
        x2 = min(w, int(x_max + padding))
        y2 = min(h, int(y_max + padding))

        # Crop
        cropped_img = pil_image.crop((x1, y1, x2, y2))
        
        # Logging token saving estimate
        orig_area = w * h
        new_area = (x2 - x1) * (y2 - y1)
        saving = (1 - (new_area / orig_area)) * 100
        logger.info(f"[CROP] Smart Crop: Reduced area by {saving:.1f}%")
        
        return cropped_img

    except Exception as e:
        logger.warning(f"Smart crop failed: {e}. Using original image.")
        return pil_image

def scan_all_pages_batch(images: List[Image.Image]) -> List[PageScanResult]:
    """
    OPTIMIZATION 1: Scans ALL pages in a SINGLE API call.
    """
    if not GRADING_CLIENT_INSTANCE or not images:
        return []

    logger.info(f"[BATCH] Starting Batch Scan for {len(images)} pages...")
    
    # Prepare prompt
    prompt_text = """
    Analyze these academic answer sheet pages.
    For EACH image, return:
    1. 'page_index': The order it appears (0, 1, 2...).
    2. 'page_number': The handwritten page number (usually top/bottom corner). Return 9999 if missing.
    3. 'has_diagram': Boolean TRUE if the page contains a hand-drawn diagram, graph, or physics sketch. FALSE for just text/equations.
    """
    
    # Combine prompt + all images
    contents = [prompt_text] + images

    try:
        response = GRADING_CLIENT_INSTANCE.generate_structured_json(
            contents=contents,
            schema=PageScanBatchResult.model_json_schema(),
            call_type_for_logging="scan_all_pages_batch"
        )

        if response.error:
            logger.error(f"Batch scan failed: {response.error}")
            return []

        # --- Metrics: Use accurate token counts from response ---
        OCR_METRICS_COLLECTOR.add_row({
            "utc_ts": datetime.now(timezone.utc).isoformat(),
            "call_type": "scan_all_pages_batch",
            "input_tokens": response.prompt_tokens,
            "output_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
            "total_cost_usd": response.cost
        })
        # ---------------

        batch_result = PageScanBatchResult.model_validate_json(response.response)
        return batch_result.results

    except Exception as e:
        logger.error(f"Batch scan exception: {e}")
        # Fallback: Return empty list, logic will handle as 'scan failed'
        return []

    
def extract_images_from_pdf(pdf_path: str) -> List[Tuple[str, Image.Image]]:
    """Extract images from PDF pages with unique naming"""
    images = []
    doc = fitz.open(pdf_path)
    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]

    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        # Create unique filename for each PDF page
        page_name = f"{pdf_name}_page{i+1:03d}.png"
        images.append((page_name, img))

    doc.close()
    return images


def images_to_pdf_bytes(images: List[Image.Image]) -> bytes:
    """Convert PIL images to PDF bytes"""
    if not images:
        return b""
    pil_images = [img.convert("RGB") for img in images]
    buf = io.BytesIO()
    pil_images[0].save(
        buf, format="PDF", save_all=True, append_images=pil_images[1:]
    )
    return buf.getvalue()

def merge_split_answers(json_data_str: str) -> str:
    """
    Parses JSON, merges continuation answers (e.g., Q1_continuation, Q3a_ii, Q4-torque)
    into their parent questions, and returns the cleaned, NATURALLY SORTED JSON string.
    """
    try:
        data = json.loads(json_data_str)
        merged_data = data.copy()
        all_keys = sorted(list(merged_data.keys()))
        keys_to_remove = set()

        # Define standard suffixes for Pass 1 & 2
        pattern = re.compile(r"^(.*?)((?:_continuation|_cont|_part)[_\s-]*\d*|_[ivx]+|_\d+)$", re.IGNORECASE)

        # --- HELPER: Merging Logic ---
        def merge_data(parent_key, child_key):
            if parent_key not in merged_data or child_key not in merged_data: return
            if parent_key == child_key: return

            parent_data = merged_data[parent_key]
            cont_data = merged_data[child_key]
            if not isinstance(parent_data, dict): parent_data = {}
            if not isinstance(cont_data, dict): cont_data = {}

            logger.info(f"[MERGE] Merging {child_key} into {parent_key}")

            # Text
            if "text" in cont_data and cont_data["text"]:
                original_text = parent_data.get("text") or ""
                new_text = cont_data["text"]
                parent_data["text"] = (original_text + "\n" + new_text).strip()

            # Equations
            if "equations" in cont_data and isinstance(cont_data["equations"], list):
                if not isinstance(parent_data.get("equations"), list):
                    parent_data["equations"] = []
                start_step = len(parent_data["equations"]) + 1
                for eq in cont_data["equations"]:
                    if isinstance(eq, dict):
                        eq["step"] = start_step 
                        start_step += 1
                    parent_data["equations"].append(eq)

            # Bullets
            if "bullets" in cont_data and isinstance(cont_data["bullets"], list):
                if not isinstance(parent_data.get("bullets"), list):
                    parent_data["bullets"] = []
                parent_data["bullets"].extend(cont_data["bullets"])

            # Tables
            if "tables" in cont_data and isinstance(cont_data["tables"], list):
                if not isinstance(parent_data.get("tables"), list):
                    parent_data["tables"] = []
                parent_data["tables"].extend(cont_data["tables"])

            # Diagrams
            if "diagram" in cont_data and isinstance(cont_data["diagram"], dict):
                if not isinstance(parent_data.get("diagram"), dict):
                    parent_data["diagram"] = {}
                existing_count = len(parent_data["diagram"])
                for d_key, d_path in cont_data["diagram"].items():
                    new_d_key = str(existing_count + 1)
                    parent_data["diagram"][new_d_key] = d_path
                    existing_count += 1

            keys_to_remove.add(child_key)
            merged_data[parent_key] = parent_data

        # --- PASS 1: PROMOTE "START" KEYS ---
        for key in all_keys:
            match = pattern.match(key)
            if match:
                base_key = match.group(1)
                suffix = match.group(2).lower()
                is_start = (suffix in ['_i', '_1'] or 'continuation_1' in suffix or 'cont_1' in suffix or suffix == '_continuation')
                if is_start and base_key not in merged_data:
                    logger.info(f"[PROMOTE] Promoting {key} to {base_key}")
                    merged_data[base_key] = merged_data[key]
                    keys_to_remove.add(key)

        for k in keys_to_remove:
            if k in merged_data: del merged_data[k]
        keys_to_remove.clear()
        all_keys = sorted(list(merged_data.keys()))

        # --- PASS 2: MERGE CONTINUATIONS ---
        for key in all_keys:
            match = pattern.match(key)
            if match:
                base_key = match.group(1)
                merge_data(base_key, key)

        for k in keys_to_remove:
            if k in merged_data: del merged_data[k]
        keys_to_remove.clear()
        all_keys = sorted(list(merged_data.keys()))

        # --- PASS 3: GENERIC PREFIX/SEPARATOR MERGE ---
        for key in all_keys:
            for potential_parent in all_keys:
                if key == potential_parent: continue
                if key.startswith(potential_parent):
                    suffix = key[len(potential_parent):]
                    if suffix and suffix[0] in ['-', '_', ' ', '.', ':']:
                        merge_data(potential_parent, key)
                        break

        for k in keys_to_remove:
            if k in merged_data: del merged_data[k]

        # --- NEW: PASS 4 - NATURAL SORTING ---
        # We create a new dictionary with keys sorted numerically (Q1, Q2, Q10...)
        def natural_sort_key(key):
            # Extract the first number found in the string
            match = re.search(r'(\d+)', key)
            if match:
                num = int(match.group(1))
                # Return tuple: (number, original_string)
                # This handles Q2 < Q10 correctly, and Q3a < Q3b correctly
                return (num, key)
            # If no number (e.g., "Introduction"), push to end
            return (float('inf'), key)

        sorted_keys = sorted(merged_data.keys(), key=natural_sort_key)
        sorted_data = {k: merged_data[k] for k in sorted_keys}

        return json.dumps(sorted_data, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error merging split answers: {e}")
        return json_data_str

def gemini_json_from_pdf(pdf_bytes: bytes, output_path: str, user_id: int) -> str:
    """Extract JSON from PDF using the specialized client."""
    if not GRADING_CLIENT_INSTANCE:
        logger.error("Gemini client not initialized. Cannot extract from PDF.")
        return json.dumps({"error": "Gemini client not initialized"}, indent=2)

    template_text = load_prompt("ocr_extraction_prompt.txt")
    prompt_text = template_text.format(output_path=output_path, user_id=user_id)

    pdf_blob = Blob(data=pdf_bytes, mime_type="application/pdf")
    pdf_part = Part(inline_data=pdf_blob)
    
    prompt_contents = [pdf_part, prompt_text]

    try:
        response = GRADING_CLIENT_INSTANCE.generate_structured_json(
            contents=prompt_contents,
            schema=OutputModel.model_json_schema(),
            call_type_for_logging="gemini_json_from_pdf"
        )
        
        if response.error:
            logger.error(f"Failed to get JSON from PDF: {response.error}")
            return json.dumps({"error": response.error}, indent=2)

        # --- Metrics: Use accurate token counts from response ---
        OCR_METRICS_COLLECTOR.add_row({
            "utc_ts": datetime.now(timezone.utc).isoformat(),
            "call_type": "gemini_json_from_pdf",
            "input_tokens": response.prompt_tokens,
            "output_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
            "total_cost_usd": response.cost,
        })
        # --- END Metrics ---

        validated_data = OutputModel.model_validate_json(response.response)
        json_str = validated_data.model_dump_json(indent=2)
        
        logger.info("Running post-processing to merge split answers...")
        merged_json_str = merge_split_answers(json_str)
        return merged_json_str

    except Exception as e:
        logger.error(f"Error getting JSON from PDF: {e}", exc_info=True)
        return json.dumps(
            {"error": f"Failed to process JSON response: {e}"},
            indent=2
        )

def get_questions_with_diagrams_on_page(
    data: Dict[str, Any], page_idx: int, total_pages: int
) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Returns ALL questions that expect a diagram. 
    We return ALL of them for every page that has a diagram, and let the
    subsequent LLM call decide which specific question the diagram belongs to.
    """
    questions_needing_diagrams = []

    for question_key, question_data in data.items():
        # Check if it looks like a question key (starts with Q, or is numeric, or like '3a')
        # and is a dictionary
        if isinstance(question_data, dict):
            # Check if 'diagram' key exists and is not None/Empty
            if "diagram" in question_data and question_data["diagram"]:
                 questions_needing_diagrams.append((question_key, question_data))
    
    return questions_needing_diagrams


def select_diagram_boxes_for_page(
    img_path: str,
    boxes: List[Tuple[int, int, int, int]],
    questions_on_page: List[Tuple[str, Dict[str, Any]]],
    output_folder: str,
) -> Dict[str, List[Tuple[int, int, int, int]]]:
    """Select bounding boxes for diagrams using Gemini and structured output."""
    if not boxes: return {}
    if not GRADING_CLIENT_INSTANCE:
        logger.error("Gemini client not initialized. Cannot select diagram boxes.")
        return {}

    # (Keep image processing logic to create combined_pil_img)
    img_cv = cv2.imread(img_path)
    combined_img = img_cv.copy()
    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = box
        cv2.rectangle(combined_img, (x1, y1), (x2, y2), (0, 255, 0), 3)
        cv2.putText(
            combined_img,
            str(i + 1),
            (x1, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 0),
            2,
        )
    combined_path = "temp_selection_for_gemini.png"
    cv2.imwrite(combined_path, combined_img)
    combined_pil_img = Image.open(combined_path)


    question_context = ""
    for question_key, question_data in questions_on_page:
        diagram_value = question_data.get("diagram")
        if isinstance(diagram_value, dict):
            diagram_count = len(diagram_value)
        else:
            diagram_count = 0
        question_context += (
            f"\n- {question_key}: Needs {diagram_count} diagram(s)."
        )

    template_text = load_prompt("select_diagram_boxes_prompt.txt")
    prompt_text = template_text.format(question_context=question_context)
    prompt_contents = [combined_pil_img, prompt_text]
    
    try:
        response = GRADING_CLIENT_INSTANCE.generate_structured_json(
            contents=prompt_contents,
            schema=DiagramSelectionResult.model_json_schema(),
            call_type_for_logging="select_diagram_boxes"
        )
        
        if response.error:
            logger.error(f"Error in diagram box selection: {response.error}")
            os.remove(combined_path)
            return {}
        
        # --- Metrics: Use accurate token counts from response ---
        OCR_METRICS_COLLECTOR.add_row({
            "utc_ts": datetime.now(timezone.utc).isoformat(),
            "call_type": "select_diagram_boxes_for_page",
            "input_tokens": response.prompt_tokens,
            "output_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
            "total_cost_usd": response.cost,
        })
        # --- END Metrics ---

        os.remove(combined_path)
        
        result = DiagramSelectionResult.model_validate_json(response.response)
        parsed_response = result.model_dump() 

        selected_boxes_dict = {}
        if parsed_response:
            for question_key, box_indices in parsed_response.items():
                coords_list = []
                for idx in box_indices:
                    if 1 <= idx <= len(boxes):
                        coords_list.append(boxes[idx - 1])
                if coords_list:
                    selected_boxes_dict[question_key] = coords_list
        
        return selected_boxes_dict

    except Exception as e:
        logger.error(f"Error in diagram box selection: {e}")
        try: os.remove(combined_path)
        except: pass
        return {}


def detect_and_crop_diagrams(
    imgs_sorted: List[Image.Image],
    json_data: str,
    output_folder: str,
    user_id: int,
    diagram_flags: List[bool]
) -> str:
    """
    Process diagrams with YOLO detection and cropping.
    MODIFIED: 
    1. Respects Pre-Scan Flags.
    2. Fixes 'media/' path issue.
    3. Fixes 'Q' prefix mismatch (Q4 vs 4).
    4. FIX: Generates URL dynamically relative to MEDIA_ROOT (Fixes 404 error).
    """
    if not YOLO_MODEL:
        logger.warning("YOLO model not loaded. Skipping diagram detection.")
        return json_data

    if len(imgs_sorted) != len(diagram_flags):
        logger.error("Length mismatch between images and flags. Skipping.")
        return json_data

    model = YOLO_MODEL
    try:
        data = json.loads(json_data)
        if "error" in data: return json_data
    except Exception as e:
        logger.error(f"Could not parse JSON: {e}")
        return json_data

    logger.info("Processing diagrams (Respecting Pre-Scan Flags)...")
    detected_diagrams_map = defaultdict(dict)
    
    questions_with_placeholders = [k for k, v in data.items() if isinstance(v, dict) and "diagram" in v]
    assigned_questions = set()

    try:
        for page_idx, img in enumerate(imgs_sorted):
            if page_idx >= len(diagram_flags): continue

            if not diagram_flags[page_idx]:
                logger.info(f"Skipping Page {page_idx+1} (Pre-scan indicated no diagram).")
                continue

            logger.info(f"Scanning Page {page_idx+1} for diagrams...")
            temp_path = os.path.join(output_folder, f"temp_page_{page_idx+1}.png")
            img.save(temp_path)

            try:
                results = model.predict(source=temp_path, imgsz=640, conf=0.10, task="detect")
                
                if results and results[0].boxes:
                    all_boxes = [tuple(map(int, b.xyxy[0].tolist())) for b in results[0].boxes]
                    
                    if all_boxes:
                        logger.info(f"Found {len(all_boxes)} boxes on Page {page_idx+1}")
                        
                        pending_questions = [
                            (k, data[k]) for k in questions_with_placeholders 
                            if k not in assigned_questions
                        ]
                        
                        if not pending_questions: 
                            logger.info("Boxes found but no questions need diagrams. Skipping.")
                            continue

                        # Smart Mapping
                        selected_boxes_dict = select_diagram_boxes_for_page(
                            temp_path, all_boxes, pending_questions, output_folder
                        )

                        # Fallback Assignment
                        if not selected_boxes_dict:
                            logger.warning(f"⚠️ LLM failed to map. Engaging FORCE ASSIGNMENT.")
                            box_areas = [(b, (b[2]-b[0])*(b[3]-b[1])) for b in all_boxes]
                            box_areas.sort(key=lambda x: x[1], reverse=True)
                            largest_box = box_areas[0][0]
                            target_q_key = pending_questions[0][0]
                            selected_boxes_dict[target_q_key] = [largest_box]
                            logger.info(f"👉 Forced assignment: Box {largest_box} -> {target_q_key}")

                        # Process assignments
                        for q_key, boxes in selected_boxes_dict.items():
                            q_match = re.search(r"Q(\d+)", q_key)
                            q_num = q_match.group(1) if q_match else "X"
                            
                            for i, box in enumerate(boxes):
                                count = len(detected_diagrams_map[q_key]) + 1
                                fname = f"Q{q_num}_{user_id}_{count}.png"
                                path = os.path.join(output_folder, fname)
                                
                                # Crop & Save
                                img_cv = cv2.imread(temp_path)
                                h, w, _ = img_cv.shape
                                x1, y1, x2, y2 = box
                                x1, y1 = max(0, x1-10), max(0, y1-10)
                                x2, y2 = min(w, x2+10), min(h, y2+10)
                                
                                cv2.imwrite(path, img_cv[y1:y2, x1:x2])
                                
                                # --- CRITICAL FIX: DYNAMIC URL GENERATION ---
                                # Use pathlib to calculate the path relative to MEDIA_ROOT
                                try:
                                    abs_path = Path(path).resolve()
                                    media_root = Path(settings.MEDIA_ROOT).resolve()
                                    
                                    # Get path relative to 'media' folder (e.g., output/284/images/file.png)
                                    rel_path = abs_path.relative_to(media_root)
                                    
                                    # Force forward slashes for URL compatibility
                                    url = str(rel_path).replace("\\", "/")
                                except Exception as e:
                                    # Fallback (Safety net)
                                    logger.warning(f"Path relative calc failed: {e}. Using fallback.")
                                    url = f"output/{os.path.basename(os.path.dirname(output_folder))}/images/{fname}"

                                detected_diagrams_map[q_key][str(count)] = url
                                assigned_questions.add(q_key)
                                logger.info(f"✅ Saved diagram for {q_key}: {url}")

            except Exception as e:
                logger.error(f"Error on Page {page_idx+1}: {e}")
            finally:
                if os.path.exists(temp_path): os.remove(temp_path)

        # Final Update of JSON
        for q_key in questions_with_placeholders:
            candidates = [q_key]
            if not q_key.startswith("Q"): candidates.append(f"Q{q_key}")
            else: candidates.append(q_key[1:])

            found_match = None
            for cand in candidates:
                if cand in detected_diagrams_map and detected_diagrams_map[cand]:
                    found_match = detected_diagrams_map[cand]
                    break
            
            if found_match:
                data[q_key]["diagram"] = found_match
                logger.info(f"✅ Diagram confirmed for {q_key}")
            else:
                logger.warning(f"No diagram found for {q_key} on flagged pages. Removing placeholder.")
                del data[q_key]["diagram"]

        return json.dumps(data, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"FATAL Diagram Logic Error: {e}")
        return json_data

def save_ocr_metrics_csv(csv_path: str):
    """
    Saves all collected OCR metrics to a CSV file.
    This should be called by your main ocr_processor.py *after* all processing is done.
    """
    logger.info("Attempting to save OCR metrics...")
    OCR_METRICS_COLLECTOR.save_csv(csv_path)


def print_ocr_metrics_summary():
    """
    Prints a summary of all collected OCR metrics to the log.
    This should be called by your main ocr_processor.py *after* all processing is done.
    """
    logger.info("Printing OCR metrics summary...")
    OCR_METRICS_COLLECTOR.print_summary()


def save_ocr_metrics_to_db(answer_upload_id: int):
    """
    Saves OCR metrics directly to the AIMetrics database model.
    Includes fallback logic if the ID passed is a User ID instead of AnswerUpload ID.
    
    Args:
        answer_upload_id: The ID of the AnswerUpload (or User ID if caller is confused).
    """
    from .models import AIMetrics, AnswerUpload
    from datetime import datetime, timezone as tz
    
    if not OCR_METRICS_COLLECTOR.rows:
        logger.info("No OCR metrics to save to DB.")
        return
    
    answer_upload = None
    
    try:
        # 1. Try treating it as an AnswerUpload ID
        answer_upload = AnswerUpload.objects.get(id=answer_upload_id)
    except AnswerUpload.DoesNotExist:
        logger.warning(f"AnswerUpload {answer_upload_id} not found by ID. Checking if it's a User ID...")
        try:
            # 2. Fallback: Try treating it as a User ID and get their latest upload
            # This fixes the specific error seen in your logs
            answer_upload = AnswerUpload.objects.filter(user_id=answer_upload_id).order_by('-upload_date').first()
            if answer_upload:
                logger.info(f"✅ Found latest AnswerUpload {answer_upload.id} for User {answer_upload_id}. Attaching metrics.")
            else:
                logger.error(f"❌ No AnswerUpload found for User ID {answer_upload_id} either.")
                return
        except Exception as e:
            logger.error(f"Error during fallback lookup: {e}")
            return

    try:
        # Clear existing OCR metrics for this upload to prevent duplicates
        AIMetrics.objects.filter(answer_upload=answer_upload, process_type='OCR').delete()
        
        # Create new metrics records
        metrics_objs = []
        for row in OCR_METRICS_COLLECTOR.rows:
            metrics_objs.append(AIMetrics(
                answer_upload=answer_upload,
                process_type='OCR',
                identifier=row.get('call_type', 'Unknown'),
                input_tokens=int(row.get('input_tokens', 0)),
                output_tokens=int(row.get('output_tokens', 0)),
                total_tokens=int(row.get('total_tokens', 0)),
                total_cost_usd=float(row.get('total_cost_usd', 0)),
                timestamp=datetime.now(tz.utc)
            ))
        
        AIMetrics.objects.bulk_create(metrics_objs)
        logger.info(f"✅ Saved {len(metrics_objs)} OCR metrics to DB for AnswerUpload {answer_upload.id}")
        
        # Clear collector after successful save to allow new tasks to start fresh
        OCR_METRICS_COLLECTOR.clear()
        
    except Exception as e:
        logger.error(f"Failed to save OCR metrics to DB: {e}", exc_info=True)


def get_ocr_metrics_totals() -> dict:
    """
    Returns the current OCR metrics totals.
    Useful for combining with grading metrics for a summary.
    """
    if not OCR_METRICS_COLLECTOR.rows:
        return {
            'input_tokens': 0,
            'output_tokens': 0, 
            'total_tokens': 0,
            'total_cost': 0.0,
            'call_count': 0
        }
    
    total_input = sum(r.get('input_tokens', 0) for r in OCR_METRICS_COLLECTOR.rows)
    total_output = sum(r.get('output_tokens', 0) for r in OCR_METRICS_COLLECTOR.rows)
    # FIX: Use the 'total_tokens' key directly if available (accurate from API)
    total_tokens = sum(r.get('total_tokens', total_input + total_output) for r in OCR_METRICS_COLLECTOR.rows)
    total_cost = sum(r.get('total_cost_usd', 0) for r in OCR_METRICS_COLLECTOR.rows)
    
    return {
        'input_tokens': total_input,
        'output_tokens': total_output,
        'total_tokens': total_tokens,
        'total_cost': total_cost,
        'call_count': len(OCR_METRICS_COLLECTOR.rows)
    }

# --- END NEW METRICS (Part 3) ---
