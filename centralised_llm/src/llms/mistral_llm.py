from ..llm_base import BaseLLM, GenerateRequest, GenerateResponse
from ..llms.together_llm_common import together_generate_and_log, together_batch_generate_and_log, handle_together_api_error
from ..utils.decorators import timeit, memory_usage
from ..utils.logging import logger
from pathlib import Path
from typing import List, Optional, Union
from ..utils.config import get_env
# from promptRightProd.settings import TOGETHER_API_KEY

class MistralLLM(BaseLLM):
    def __init__(self, api_key: str, model: str = "mistralai/Mixtral-8x7B-Instruct-v0.1", 
                 temperature: float = 0.7, max_tokens: int = 512, 
                 stop: Optional[Union[str, List[str]]] = None, top_p: float = 0.7, 
                 top_k: int = 50, repetition_penalty: float = 1.0, 
                 stream_tokens: bool = False, safety_model: Optional[str] = None, 
                 n: int = 1):
        """
        Initialize MistralLLM with all Mistral API parameters.
        
        Args:
            api_key: Together API key for Mistral models
            model: Model name (default: mistralai/Mixtral-8x7B-Instruct-v0.1)
            temperature: Randomness in response (0.0-1.0, default: 0.7)
            max_tokens: Maximum tokens to generate (default: 512)
            stop: Stop sequences (default: ["</s>", "[/INST]"])
            top_p: Nucleus sampling parameter (default: 0.7)
            top_k: Top-k sampling parameter (default: 50)
            repetition_penalty: Controls repetition (default: 1.0)
            stream_tokens: Stream response tokens (default: False)
            safety_model: Safety model to use (optional)
            n: Number of completions to generate (default: 1)
        """
        env_key =get_env('TOGETHER_API_KEY')
        self.api_key = env_key if env_key else api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stop = stop if stop is not None else ["</s>", "[/INST]"]
        self.top_p = top_p
        self.top_k = top_k
        self.repetition_penalty = repetition_penalty
        self.stream_tokens = stream_tokens
        self.safety_model = safety_model
        self.n = n
        self.pricing_json_path = Path(__file__).parent.parent / 'config' / 'llm_pricing.json'
        self.provider_key = "Mistral AI"

    @timeit
    @memory_usage
    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        try:
            user_params = request.parameters or {}
            # Override instance params with user_params if provided
            temp = user_params.get('temperature', self.temperature)
            max_tok = user_params.get('max_tokens', self.max_tokens)
            stop_param = user_params.get('stop', self.stop)
            top_p_param = user_params.get('top_p', self.top_p)
            top_k_param = user_params.get('top_k', self.top_k)
            repetition_penalty_param = user_params.get('repetition_penalty', self.repetition_penalty)
            stream_tokens_param = user_params.get('stream_tokens', self.stream_tokens)
            safety_model_param = user_params.get('safety_model', self.safety_model)
            n_param = user_params.get('n', self.n)

            return await together_generate_and_log(
                prompt=request.prompt,
                model=self.model,
                api_key=self.api_key,
                temperature=temp,
                max_tokens=max_tok,
                stop=stop_param,
                top_p=top_p_param,
                top_k=top_k_param,
                repetition_penalty=repetition_penalty_param,
                stream_tokens=stream_tokens_param,
                safety_model=safety_model_param,
                n=n_param,
                pricing_json_path=self.pricing_json_path,
                provider_key=self.provider_key,
                user_params=user_params
            )
        except Exception as e:
            logger.error(f"Mistral generation failed: {e}")
            error_message = handle_together_api_error(e, self.model)
            return GenerateResponse(
                response="",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                cost=0,
                model=self.model,
                error=error_message
            )

    # --------- Batching support ---------
    async def batch_generate(self, requests: List[GenerateRequest]) -> List[GenerateResponse]:
        try:
            prompts = [req.prompt for req in requests]
            user_params = requests[0].parameters if requests else None
            # Override instance params with user_params if provided
            temp = user_params.get('temperature', self.temperature) if user_params else self.temperature
            max_tok = user_params.get('max_tokens', self.max_tokens) if user_params else self.max_tokens
            stop_param = user_params.get('stop', self.stop) if user_params else self.stop
            top_p_param = user_params.get('top_p', self.top_p) if user_params else self.top_p
            top_k_param = user_params.get('top_k', self.top_k) if user_params else self.top_k
            repetition_penalty_param = user_params.get('repetition_penalty', self.repetition_penalty) if user_params else self.repetition_penalty
            stream_tokens_param = user_params.get('stream_tokens', self.stream_tokens) if user_params else self.stream_tokens
            safety_model_param = user_params.get('safety_model', self.safety_model) if user_params else self.safety_model
            n_param = user_params.get('n', self.n) if user_params else self.n

            return await together_batch_generate_and_log(
                prompts=prompts,
                model=self.model,
                api_key=self.api_key,
                temperature=temp,
                max_tokens=max_tok,
                stop=stop_param,
                top_p=top_p_param,
                top_k=top_k_param,
                repetition_penalty=repetition_penalty_param,
                stream_tokens=stream_tokens_param,
                safety_model=safety_model_param,
                n=n_param,
                pricing_json_path=self.pricing_json_path,
                provider_key=self.provider_key,
                user_params=user_params
            )
        except Exception as e:
            logger.error(f"Mistral batch generation failed: {e}")
            error_message = handle_together_api_error(e, self.model)
            return [GenerateResponse(
                response="",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                cost=0.0,
                model=self.model,
                error=error_message
            ) for _ in requests]
