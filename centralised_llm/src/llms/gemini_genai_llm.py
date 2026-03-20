# gemini_grading_client.py
import os
import io
import time
import json
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import google.genai as genai
from google.genai.types import HarmCategory, HarmBlockThreshold, GenerateContentResponse

# Setup logger
logger = logging.getLogger(__name__)

# --- Response Model ---
class GenerateResponse(BaseModel):
    """A standardized response object for all client calls."""
    response: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    model: str = ""
    error: Optional[str] = None

# --- Main Client Class ---
class GeminiGradingClient:
    """
    A specialized, robust client for the AI Grading pipeline.
    It handles structured JSON output, cost/token tracking,
    detailed error handling, and automatic retries.
    """
    
    def __init__(self, 
                 model_name: Optional[str] = None):
        
        # Load configuration
        self.config = self._load_config()
        
        # Determine model name (arg > config > default)
        self.model_name = model_name or self.config.get("model", "gemini-3-flash-preview")
        self.max_retries = self.config.get("max_retries", 3)
        
        api_key = os.getenv("GEMINI_API_KEY") or self.config.get("api_key")
        if not api_key:
            logger.critical("GEMINI_API_KEY not found in .env file or config")
            raise ValueError("GEMINI_API_KEY not found")
        
        self.client = genai.Client(api_key=api_key)
        
        # Parse safety settings from config
        self.safety_settings = self._parse_safety_settings(self.config.get("safety_settings"))
        
        self.pricing_data = self._load_pricing_data()

    def _load_config(self) -> Dict:
        """Loads model configuration from central config."""
        config_path = Path(__file__).parent.parent / 'config' / 'llm_config.json'
        try:
            with open(config_path) as f:
                data = json.load(f)
                return data.get('gemini', {})
        except Exception as e:
            logger.error(f"Error loading model config: {e}")
            return {}

    def _parse_safety_settings(self, settings_list: List[Dict]) -> List[Dict]:
        """Converts string-based safety settings from JSON to genai Types."""
        if not settings_list:
            # Default fallback if config is missing
            return [
                {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
                {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_NONE},
                {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_NONE},
                {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_NONE}
            ]
            
        parsed_settings = []
        for s in settings_list:
            try:
                # Map string keys to Enum values if needed, otherwise pass through
                # The google-genai library often accepts string names for categories/thresholds directly
                # but explicit mapping is safer if strings are used in JSON.
                # Assuming library handles strings or we map them here.
                # Simplest path: Pass dictionaries directly as the SDK supports dicts for safety_settings
                parsed_settings.append(s)
            except Exception as e:
                logger.warning(f"Failed to parse safety setting {s}: {e}")
        
        return parsed_settings
        
        self.pricing_data = self._load_pricing_data()

    def _load_pricing_data(self) -> Dict:
        """Loads pricing data from central config."""
        pricing_path = Path(__file__).parent.parent / 'config' / 'llm_pricing.json'
        try:
            with open(pricing_path) as f:
                data = json.load(f)
                return data.get('pricing', {}).get('Gemini', {})
        except Exception as e:
            logger.error(f"Error loading pricing data: {e}")
            return {}

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int, is_batch: bool = False) -> float:
        """
        Calculate cost based on token usage and loaded pricing (per 1k tokens).
        """
        try:
            # Determine the correct pricing key
            pricing_key = self.model_name
            # Note: Batch extensions not yet in JSON, logical fallback needed if strictly required, 
            # but assuming standard key lookup for now as per user request to move to config.
            
            model_pricing = self.pricing_data.get(pricing_key)
            
            # Fallback for preview models or mismatches
            if not model_pricing:
                 for key in self.pricing_data:
                    if key in self.model_name:
                        model_pricing = self.pricing_data[key]
                        break
            
            if not model_pricing:
                logger.warning(f"No pricing data for {pricing_key}. Cost is 0.")
                return 0.0

            input_cost = 0.0
            output_cost = 0.0

            # Check for Tiered Pricing properties in the loaded config
            if "tier_1_limit" in model_pricing:
                limit = model_pricing.get("tier_1_limit", 200_000)
                
                if prompt_tokens <= limit:
                    input_rate = model_pricing.get("input", 0)       # Tier 1 is standard 'input'
                    output_rate = model_pricing.get("output", 0)     # Tier 1 is standard 'output'
                else:
                    input_rate = model_pricing.get("input_tier_2", 0)
                    output_rate = model_pricing.get("output_tier_2", 0)
                
                # Config is per 1k tokens
                input_cost = (prompt_tokens / 1000) * input_rate
                output_cost = (completion_tokens / 1000) * output_rate
            
            # Standard Pricing
            else:
                input_rate = model_pricing.get("input", 0) 
                output_rate = model_pricing.get("output", 0)
                
                input_cost = (prompt_tokens / 1000) * input_rate
                output_cost = (completion_tokens / 1000) * output_rate
            
            return input_cost + output_cost
            
        except Exception as e:
            logger.warning(f"Cost calculation failed: {e}")
            return 0.0

    def _extract_token_usage(self, response: GenerateContentResponse) -> tuple:
        """Extract token usage from Gemini response"""
        try:
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                prompt_tokens = getattr(usage, 'prompt_token_count', 0)
                # Output price includes thinking tokens, so 'candidates_token_count' is correct
                completion_tokens = getattr(usage, 'candidates_token_count', 0)
                total_tokens = getattr(usage, 'total_token_count', prompt_tokens + completion_tokens)
                return prompt_tokens, completion_tokens, total_tokens
            
            # Fallback for safety-blocked or empty responses
            return 0, 0, 0
        except Exception as e:
            logger.warning(f"Token usage extraction failed: {e}")
            return 0, 0, 0

    def _handle_error(self, error: Exception) -> GenerateResponse:
        """Handle Gemini API specific errors and return a standard Response object"""
        error_str = str(error).lower()
        error_message = ""
        
        # Parse common Gemini API error patterns
        if "400" in error_str and "invalid_argument" in error_str:
            error_message = "Invalid Argument: The request body is malformed. Check the API reference."
        elif "400" in error_str and "failed_precondition" in error_str:
            error_message = "Failed Precondition: Gemini API free tier is not available. Please enable billing."
        elif "403" in error_str:
            error_message = "Permission Denied: Your API key doesn't have the required permissions."
        elif "404" in error_str:
            error_message = "Not Found: The requested resource wasn't found. Check the model name."
        elif "429" in error_str:
            error_message = "Resource Exhausted: You've exceeded the rate limit. Please wait and retry."
        elif "500" in error_str:
            error_message = "Internal Error: An unexpected error occurred on Google's side."
        elif "503" in error_str:
            error_message = "Service Unavailable: The service may be temporarily overloaded."
        elif "timeout" in error_str:
            error_message = "Request Timeout: The request took too long to process."
        elif "api key" in error_str:
            error_message = "API Key Error: Please check your Google API key is valid."
        else:
            error_message = f"Gemini API Error: {str(error)}"
        
        logger.error(f"Gemini API Error: {error_message}")
        
        return GenerateResponse(
            model=self.model_name,
            error=error_message
        )

    def generate_structured_json(
        self,
        contents: List[Any],
        schema: Dict[str, Any],
        call_type_for_logging: str = "structured_call"
    ) -> GenerateResponse:
        """
        Generates structured JSON content from Gemini.
        This is the primary method for the grading pipeline.
        """
        
        # Define the generation config
        # Use config values, falling back to defaults if missing
        config_dict = {
            "temperature": self.config.get("temperature", 0.2),
            "top_p": self.config.get("top_p", 0.95),
            "top_k": self.config.get("top_k", 40),
            "candidate_count": self.config.get("n", 1),
            "max_output_tokens": self.config.get("max_tokens", 65536),
            "response_mime_type": "application/json",
            "response_json_schema": schema,
            "safety_settings": self.safety_settings
        }

        for attempt in range(self.max_retries):
            try:
                logger.info(
                    f"Attempt {attempt + 1}/{self.max_retries} for {call_type_for_logging}..."
                )
                
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config_dict,
                )
                
                response_text = response.text
                prompt_tokens, completion_tokens, total_tokens = self._extract_token_usage(response)
                
                # Handle safety blocks which have no text
                if not response_text and hasattr(response, 'prompt_feedback'):
                    if response.prompt_feedback.block_reason:
                        error_msg = f"Content blocked: {response.prompt_feedback.block_reason}"
                        logger.error(error_msg)
                        return GenerateResponse(model=self.model_name, error=error_msg)

                # Calculate cost (now with tiered logic)
                cost = self._calculate_cost(prompt_tokens, completion_tokens)
                
                logger.info(f"[OK] Success: {call_type_for_logging} | Cost: ${cost:.6f} | Tokens: {total_tokens}")

                return GenerateResponse(
                    response=response_text,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    cost=cost,
                    model=self.model_name
                )

            except Exception as e:
                logger.warning(
                    f"Error on attempt {attempt + 1} for {call_type_for_logging}: {e}", 
                    exc_info=False # Set to True for full stack trace
                )
                if "429" in str(e) or "quota" in str(e).lower():
                    wait_time = 10 + (attempt * 5) # Exponential backoff
                    logger.warning(f"Rate limit hit. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                elif attempt < self.max_retries - 1:
                    wait_time = 5 + (attempt * 2)
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"All retries failed for {call_type_for_logging}.")
                    # This is the final failure, so pass to detailed error handler
                    return self._handle_error(e)

        # Fallback (should be unreachable)
        return self._handle_error(Exception(f"Failed to get response for {call_type_for_logging}"))