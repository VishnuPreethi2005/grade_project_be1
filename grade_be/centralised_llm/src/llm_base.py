from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

class GenerateRequest(BaseModel):
    model: str
    prompt: str
    parameters: Optional[Dict[str, Any]] = None

class GenerateResponse(BaseModel):
    response: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    model: str
    error: Optional[str] = None

class BaseLLM(ABC):
    @abstractmethod
    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        pass

    @abstractmethod
    async def batch_generate(self, requests: List[GenerateRequest]) -> List[GenerateResponse]:
        pass

class CallbackCapableLLM(BaseLLM):
    @abstractmethod
    def get_callback_params(self) -> Dict[str, Any]:
        pass

class ErrorHandlingLLM(BaseLLM):
    """
    Abstract class for LLMs that need custom error handling strategies.
    Developers can inherit this to implement model-specific error handling.
    """
    
    @abstractmethod
    def handle_error(self, error: Exception, request: GenerateRequest) -> GenerateResponse:
        """
        Handle any type of error that occurs during LLM API calls.
        Returns a GenerateResponse with appropriate error message and fallback values.
        """
        pass
