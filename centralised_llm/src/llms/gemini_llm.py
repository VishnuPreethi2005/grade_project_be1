import logging
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types

# Import your existing base classes
from ..llm_base import ErrorHandlingLLM, BaseLLM, GenerateRequest, GenerateResponse
from ..utils.decorators import timeit, memory_usage
from ..utils.config import get_env

logger = logging.getLogger(__name__)

class GeminiLLM(ErrorHandlingLLM, BaseLLM):
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", 
                 temperature: float = 0.7, max_tokens: int = 8192, 
                 top_p: float = 0.95, top_k: int = 40, **kwargs):
        """
        Initialize Gemini LLM using the google-genai SDK.
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.top_k = top_k
        
        if kwargs:
            logger.debug(f"GeminiLLM: Ignoring unsupported init parameters: {kwargs.keys()}")

        env_key = get_env("GEMINI_API_KEY")
        self.api_key = env_key if env_key else api_key
        
        if not self.api_key:
            logger.error("Gemini API Key is missing. Please set GEMINI_API_KEY environment variable.")

        self.client = genai.Client(api_key=self.api_key)

    def handle_error(self, error: Exception, request: GenerateRequest) -> GenerateResponse:
        error_msg = str(error)
        logger.error(f"Gemini API Error for {request.model}: {error_msg}")
        
        return GenerateResponse(
            response="",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost=0.0,
            model=self.model,
            error=f"Gemini Error: {error_msg}"
        )

    @timeit
    @memory_usage
    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        try:
            params = request.parameters or {}
            
            config = types.GenerateContentConfig(
                temperature=params.get("temperature", self.temperature),
                max_output_tokens=params.get("max_tokens", self.max_tokens),
                top_p=params.get("top_p", self.top_p),
                top_k=params.get("top_k", self.top_k),
            )

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=request.prompt,
                config=config
            )

            # --- FIX: Strict None Checking for Token Counts ---
            usage = response.usage_metadata
            p_tokens = 0
            c_tokens = 0
            total_tokens = 0
            
            if usage:
                p_tokens = usage.prompt_token_count if usage.prompt_token_count is not None else 0
                c_tokens = usage.candidates_token_count if usage.candidates_token_count is not None else 0
                total_tokens = usage.total_token_count if usage.total_token_count is not None else 0
            # --------------------------------------------------

            response_text = response.text if response.text else ""

            return GenerateResponse(
                response=response_text,
                prompt_tokens=p_tokens,
                completion_tokens=c_tokens,
                total_tokens=total_tokens,
                cost=0.0, 
                model=self.model
            )

        except Exception as e:
            return self.handle_error(e, request)

    async def batch_generate(self, requests: List[GenerateRequest]) -> List[GenerateResponse]:
        import asyncio
        tasks = [self.generate(req) for req in requests]
        return await asyncio.gather(*tasks)
