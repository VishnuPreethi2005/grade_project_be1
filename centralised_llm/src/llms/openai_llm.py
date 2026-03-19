import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import logging
from langchain_openai import ChatOpenAI
from langchain_community.callbacks import get_openai_callback
import mlflow
from ..llm_base import CallbackCapableLLM, ErrorHandlingLLM, BaseLLM, GenerateRequest, GenerateResponse
from ..utils.decorators import timeit, memory_usage
from ..utils.logging import logger
from ..utils.config import get_env

class OpenAILLM(CallbackCapableLLM, ErrorHandlingLLM, BaseLLM):
    def __init__(self, api_key: str, model: str, temperature: float = 0.7, 
                 max_tokens: int = 512, top_p: float = 1.0, n: int = 1, 
                 stop: Optional[Union[str, List[str]]] = None, 
                 frequency_penalty: float = 0.0, presence_penalty: float = 0.0):
        """
        Initialize OpenAILLM with all ChatCompletion API parameters.
        
        Args:
            api_key: OpenAI API key
            model: Model name to use
            temperature: Sampling temperature (0.2 to 0.8)
            max_tokens: Maximum tokens to generate (256)
            top_p: Nucleus sampling parameter (0.3 to 0.9)
            n: Number of responses (1, 2 or 3)
            stop: Stop conditions for model (String/list of string)
            frequency_penalty: Control repetitive responses (0.6 to 1)
            presence_penalty: Avoid certain topics in response (0.2 to 0.6)
        """
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.n = n
        self.stop = stop
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.model = model
        
        env_key = get_env("OPENAI_API_KEY")
        self.api_key = env_key if env_key else api_key
        self.pricing_data = self._load_pricing_data()
        self.llm = self._configure_llm()
        self.logger = logging.getLogger(f"{self.__class__.__name__}")

    def _load_pricing_data(self) -> Dict:
        pricing_path = Path(__file__).parent.parent / 'config' / 'llm_pricing.json'
        try:
            import json
            with open(pricing_path) as f:
                return json.load(f)['pricing']['OpenAI']
        except Exception as e:
            logger.error(f"Error loading pricing data: {e}")
            return {}

    def _configure_llm(self):
        """Configure the LLM with all parameters."""
        llm_params = {
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "n": self.n,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty
        }
        
        # Add stop parameter if provided
        if self.stop is not None:
            llm_params["stop"] = self.stop
            
        # Only use regular OpenAI ChatOpenAI (no Azure configuration)
        return ChatOpenAI(
            api_key=self.api_key,
            model=self.model,
            **llm_params
        )

    def get_callback_params(self) -> Dict[str, Any]:
        return {"callback_manager": get_openai_callback()}

    def handle_error(self, error: Exception, request: GenerateRequest) -> GenerateResponse:
        """
        Handle OpenAI API specific errors.
        Returns a GenerateResponse with appropriate error message and fallback values.
        """
        error_str = str(error).lower()
        error_message = ""
        
        # Parse OpenAI API error codes - CHECK 401 FIRST before checking for region/country
        if "401" in error_str:
            if "invalid authentication" in error_str:
                error_message = "Invalid Authentication: Ensure the correct API key and requesting organization are being used."
            elif "incorrect api key" in error_str:
                error_message = "Incorrect API key provided: Ensure the API key used is correct, clear your browser cache, or generate a new one."
            elif "member of an organization" in error_str:
                error_message = "You must be a member of an organization to use the API: Contact support to get added to a new organization."
            elif "access denied" in error_str or "subscription key" in error_str:
                error_message = "Access denied due to invalid subscription key or wrong API endpoint: Make sure to provide a valid key for an active subscription and use a correct regional API endpoint for your resource."
            else:
                error_message = "Authentication Error: Invalid or missing API credentials."
        elif "403" in error_str or ("country" in error_str and "401" not in error_str) or ("region" in error_str and "401" not in error_str):
            error_message = "Country, region, or territory not supported: Please check supported regions for more information."
        elif "429" in error_str and "rate limit" in error_str:
            error_message = "Rate limit reached for requests: You are sending requests too quickly. Please pace your requests."
        elif "429" in error_str and "quota" in error_str:
            error_message = "You exceeded your current quota: You have run out of credits or hit your maximum monthly spend. Buy more credits or increase your limits."
        elif "500" in error_str or "server error" in error_str:
            error_message = "The server had an error while processing your request: Retry your request after a brief wait and contact us if the issue persists."
        elif "503" in error_str and "overloaded" in error_str:
            error_message = "The engine is currently overloaded: Please try again later."
        elif "503" in error_str and "slow down" in error_str:
            error_message = "Slow Down: Please reduce your request rate to its original level, maintain a consistent rate for at least 15 minutes, and then gradually increase it."
        else:
            error_message = f"OpenAI API Error: {str(error)}"
        
        # Log the error
        self.logger.error(f"OpenAI API Error in {request.model}: {str(error)}")
        self.logger.error(f"Request details - Prompt: {request.prompt[:100]}..., Parameters: {request.parameters}")
        
        return GenerateResponse(
            response="",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost=0.0,
            model=request.model,
            error=error_message
        )

    @timeit
    @memory_usage
    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        try:
            params = request.parameters or {}
            with get_openai_callback() as cb:
                response = await self.llm.ainvoke(request.prompt, **params)
            cost = self._calculate_cost(cb)
            # self._log_to_mlflow(request, cb, cost)
            return GenerateResponse(
                response=response.content,
                prompt_tokens=cb.prompt_tokens,
                completion_tokens=cb.completion_tokens,
                total_tokens=cb.total_tokens,
                cost=cost,
                model=self.model
            )
        except Exception as e:
            logger.error(f"OpenAI generation failed: {e}")
            # Use the abstract handle_error method
            return self.handle_error(e, request)

    def _calculate_cost(self, cb) -> float:
        try:
            model_pricing = self.pricing_data.get(self.model, {})
            return (cb.prompt_tokens * model_pricing.get('input', 0) / 1000 +
                    cb.completion_tokens * model_pricing.get('output', 0) / 1000)
        except Exception as e:
            logger.warning(f"Cost calculation failed: {e}")
            return 0.0

    # def _log_to_mlflow(self, request, cb, cost):
    #     with mlflow.start_run(nested=True,run_name=f"OpenAI_{self.model}"):
    #         mlflow.log_params({
    #             "model": self.model,
    #             "temperature": self.temperature,
    #             "max_tokens": self.max_tokens,
    #             "top_p": self.top_p,
    #             "n": self.n,
    #             "stop": self.stop,
    #             "frequency_penalty": self.frequency_penalty,
    #             "presence_penalty": self.presence_penalty
    #         })
    #         mlflow.log_metrics({
    #             "prompt_tokens": cb.prompt_tokens,
    #             "completion_tokens": cb.completion_tokens,
    #             "total_tokens": cb.total_tokens,
    #             "cost": cost
    #         })
    #         mlflow.log_text(request.prompt, "prompt.txt")

    # --------- Batching support ---------
    async def batch_generate(self, requests: List[GenerateRequest]) -> List[GenerateResponse]:
        prompts = [req.prompt for req in requests]
        params = requests[0].parameters or {} if requests else {}
        try:
            with get_openai_callback() as cb:
                responses = await self.llm.abatch(prompts, **params)
            
            # Calculate total cost for the entire batch
            total_cost = self._calculate_cost(cb)
            
            # Distribute tokens and cost evenly across responses (approximation)
            num_requests = len(requests)
            prompt_tokens_per = cb.prompt_tokens // num_requests if num_requests > 0 else 0
            completion_tokens_per = cb.completion_tokens // num_requests if num_requests > 0 else 0
            cost_per = total_cost / num_requests if num_requests > 0 else 0
            
            results = []
            for req, resp in zip(requests, responses):
                results.append(GenerateResponse(
                    response=resp.content,
                    prompt_tokens=prompt_tokens_per,
                    completion_tokens=completion_tokens_per,
                    total_tokens=prompt_tokens_per + completion_tokens_per,
                    cost=cost_per,
                    model=self.model
                ))
            
            # Log batch metrics to MLflow
            # with mlflow.start_run(nested=True):
            #     mlflow.log_params({
            #         "model": self.model,
            #         "temperature": self.temperature,
            #         "max_tokens": self.max_tokens,
            #         "top_p": self.top_p,
            #         "n": self.n,
            #         "stop": self.stop,
            #         "frequency_penalty": self.frequency_penalty,
            #         "presence_penalty": self.presence_penalty,
            #         "batch_size": num_requests
            #     })
            #     mlflow.log_metrics({
            #         "total_prompt_tokens": cb.prompt_tokens,
            #         "total_completion_tokens": cb.completion_tokens,
            #         "total_cost": total_cost
            #     })
            
            return results
        except Exception as e:
            logger.error(f"OpenAI batch generation failed: {e}")
            # Use the abstract handle_error method for each request
            return [self.handle_error(e, req) for req in requests]
