# test_llm_base.py
import pytest
import sys
from pathlib import Path
from abc import ABC

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.llm_base import BaseLLM, CallbackCapableLLM, ErrorHandlingLLM, GenerateRequest, GenerateResponse


class TestLLMBase:
    """Test suite for LLM base classes and models."""

    # ============================================================================
    # PYDANTIC MODEL TESTS
    # ============================================================================

    def test_generate_request_creation(self):
        """Test GenerateRequest model creation."""
        request = GenerateRequest(
            model="test-model",
            prompt="Test prompt",
            parameters={"temperature": 0.7, "max_tokens": 100}
        )
        
        assert request.model == "test-model"
        assert request.prompt == "Test prompt"
        assert request.parameters == {"temperature": 0.7, "max_tokens": 100}

    def test_generate_request_without_parameters(self):
        """Test GenerateRequest model creation without parameters."""
        request = GenerateRequest(
            model="test-model",
            prompt="Test prompt"
        )
        
        assert request.model == "test-model"
        assert request.prompt == "Test prompt"
        assert request.parameters is None

    def test_generate_response_creation(self):
        """Test GenerateResponse model creation."""
        response = GenerateResponse(
            response="Test response",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            cost=0.005,
            model="test-model"
        )
        
        assert response.response == "Test response"
        assert response.prompt_tokens == 10
        assert response.completion_tokens == 20
        assert response.total_tokens == 30
        assert response.cost == 0.005
        assert response.model == "test-model"
        assert response.error is None

    def test_generate_response_with_error(self):
        """Test GenerateResponse model creation with error."""
        response = GenerateResponse(
            response="",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost=0.0,
            model="test-model",
            error="API Error occurred"
        )
        
        assert response.response == ""
        assert response.prompt_tokens == 0
        assert response.completion_tokens == 0
        assert response.total_tokens == 0
        assert response.cost == 0.0
        assert response.model == "test-model"
        assert response.error == "API Error occurred"

    # ============================================================================
    # ABSTRACT BASE CLASS TESTS
    # ============================================================================

    def test_base_llm_cannot_instantiate(self):
        """Test that BaseLLM cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class BaseLLM"):
            BaseLLM()

    def test_callback_llm_cannot_instantiate(self):
        """Test that CallbackCapableLLM cannot be instantiated with missing methods."""
        class Dummy(CallbackCapableLLM):
            async def generate(self, request: GenerateRequest):
                pass
            async def batch_generate(self, requests):
                pass
            # Missing get_callback_params method
        
        with pytest.raises(TypeError, match="Can't instantiate abstract class Dummy"):
            Dummy()

    def test_error_handling_llm_cannot_instantiate(self):
        """Test that ErrorHandlingLLM cannot be instantiated with missing methods."""
        class DummyErrorHandling(ErrorHandlingLLM):
            async def generate(self, request: GenerateRequest):
                pass
            async def batch_generate(self, requests):
                pass
            # Missing handle_error method
        
        with pytest.raises(TypeError, match="Can't instantiate abstract class DummyErrorHandling"):
            DummyErrorHandling()

    # ============================================================================
    # CONCRETE IMPLEMENTATION TESTS
    # ============================================================================

    def test_concrete_llm_instantiation(self):
        """Test that concrete BaseLLM implementation can be instantiated."""
        class ConcreteLLM(BaseLLM):
            async def generate(self, request: GenerateRequest) -> GenerateResponse:
                return GenerateResponse(
                    response="Test response",
                    prompt_tokens=10,
                    completion_tokens=20,
                    total_tokens=30,
                    cost=0.005,
                    model=request.model
                )
            
            async def batch_generate(self, requests):
                return [await self.generate(req) for req in requests]
        
        llm = ConcreteLLM()
        assert llm is not None
        assert isinstance(llm, BaseLLM)

    def test_concrete_callback_llm_instantiation(self):
        """Test that concrete CallbackCapableLLM implementation can be instantiated."""
        class ConcreteCallbackLLM(CallbackCapableLLM):
            def get_callback_params(self):
                return {"callback_manager": "test_callback"}
            
            async def generate(self, request: GenerateRequest) -> GenerateResponse:
                return GenerateResponse(
                    response="Test response",
                    prompt_tokens=10,
                    completion_tokens=20,
                    total_tokens=30,
                    cost=0.005,
                    model=request.model
                )
            
            async def batch_generate(self, requests):
                return [await self.generate(req) for req in requests]
        
        llm = ConcreteCallbackLLM()
        assert llm is not None
        assert isinstance(llm, CallbackCapableLLM)
        assert isinstance(llm, BaseLLM)
        assert llm.get_callback_params() == {"callback_manager": "test_callback"}

    def test_concrete_error_handling_llm_instantiation(self):
        """Test that concrete ErrorHandlingLLM implementation can be instantiated."""
        class ConcreteErrorHandlingLLM(ErrorHandlingLLM):
            def handle_error(self, error: Exception, request: GenerateRequest) -> GenerateResponse:
                return GenerateResponse(
                    response="",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    cost=0.0,
                    model=request.model,
                    error=str(error)
                )
            
            async def generate(self, request: GenerateRequest) -> GenerateResponse:
                return GenerateResponse(
                    response="Test response",
                    prompt_tokens=10,
                    completion_tokens=20,
                    total_tokens=30,
                    cost=0.005,
                    model=request.model
                )
            
            async def batch_generate(self, requests):
                return [await self.generate(req) for req in requests]
        
        llm = ConcreteErrorHandlingLLM()
        assert llm is not None
        assert isinstance(llm, ErrorHandlingLLM)
        assert isinstance(llm, BaseLLM)
        
        # Test error handling
        request = GenerateRequest(model="test", prompt="test")
        error_response = llm.handle_error(Exception("Test error"), request)
        assert error_response.error == "Test error"
        assert error_response.response == ""
        assert error_response.cost == 0.0

    # ============================================================================
    # MULTIPLE INHERITANCE TESTS
    # ============================================================================

    def test_multiple_inheritance_combination(self):
        """Test that multiple inheritance works correctly."""
        class MultiInheritanceLLM(CallbackCapableLLM, ErrorHandlingLLM):
            def get_callback_params(self):
                return {"callback": "multi_callback"}
            
            def handle_error(self, error: Exception, request: GenerateRequest) -> GenerateResponse:
                return GenerateResponse(
                    response="",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    cost=0.0,
                    model=request.model,
                    error=f"Multi error: {str(error)}"
                )
            
            async def generate(self, request: GenerateRequest) -> GenerateResponse:
                return GenerateResponse(
                    response="Multi response",
                    prompt_tokens=15,
                    completion_tokens=25,
                    total_tokens=40,
                    cost=0.008,
                    model=request.model
                )
            
            async def batch_generate(self, requests):
                return [await self.generate(req) for req in requests]
        
        llm = MultiInheritanceLLM()
        assert llm is not None
        assert isinstance(llm, CallbackCapableLLM)
        assert isinstance(llm, ErrorHandlingLLM)
        assert isinstance(llm, BaseLLM)
        
        # Test both capabilities
        assert llm.get_callback_params() == {"callback": "multi_callback"}
        
        request = GenerateRequest(model="test", prompt="test")
        error_response = llm.handle_error(Exception("Test"), request)
        assert "Multi error: Test" in error_response.error

    # ============================================================================
    # ASYNC METHOD TESTS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_concrete_llm_generate_method(self):
        """Test that concrete LLM generate method works."""
        class TestLLM(BaseLLM):
            async def generate(self, request: GenerateRequest) -> GenerateResponse:
                return GenerateResponse(
                    response=f"Generated response for: {request.prompt}",
                    prompt_tokens=len(request.prompt.split()),
                    completion_tokens=10,
                    total_tokens=len(request.prompt.split()) + 10,
                    cost=0.001,
                    model=request.model
                )
            
            async def batch_generate(self, requests):
                return [await self.generate(req) for req in requests]
        
        llm = TestLLM()
        request = GenerateRequest(
            model="test-model",
            prompt="This is a test prompt",
            parameters={"temperature": 0.5}
        )
        
        response = await llm.generate(request)
        
        assert response.response == "Generated response for: This is a test prompt"
        assert response.prompt_tokens == 5  # 5 words in prompt
        assert response.completion_tokens == 10
        assert response.total_tokens == 15
        assert response.cost == 0.001
        assert response.model == "test-model"
        assert response.error is None

    @pytest.mark.asyncio
    async def test_concrete_llm_batch_generate_method(self):
        """Test that concrete LLM batch_generate method works."""
        class TestLLM(BaseLLM):
            async def generate(self, request: GenerateRequest) -> GenerateResponse:
                return GenerateResponse(
                    response=f"Response for: {request.prompt}",
                    prompt_tokens=5,
                    completion_tokens=10,
                    total_tokens=15,
                    cost=0.001,
                    model=request.model
                )
            
            async def batch_generate(self, requests):
                return [await self.generate(req) for req in requests]
        
        llm = TestLLM()
        requests = [
            GenerateRequest(model="test", prompt="First prompt"),
            GenerateRequest(model="test", prompt="Second prompt")
        ]
        
        responses = await llm.batch_generate(requests)
        
        assert len(responses) == 2
        assert responses[0].response == "Response for: First prompt"
        assert responses[1].response == "Response for: Second prompt"
        assert all(isinstance(resp, GenerateResponse) for resp in responses)

    # ============================================================================
    # VALIDATION TESTS
    # ============================================================================

    def test_generate_request_validation(self):
        """Test GenerateRequest validation."""
        # Test missing required fields
        with pytest.raises(ValueError):
            GenerateRequest()  # Missing model and prompt
        
        with pytest.raises(ValueError):
            GenerateRequest(model="test")  # Missing prompt
        
        with pytest.raises(ValueError):
            GenerateRequest(prompt="test")  # Missing model

    def test_generate_response_validation(self):
        """Test GenerateResponse validation."""
        # Test missing required fields
        with pytest.raises(ValueError):
            GenerateResponse()  # Missing all required fields
        
        # Test with all required fields
        response = GenerateResponse(
            response="test",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            cost=0.005,
            model="test-model"
        )
        assert response is not None

    def test_pydantic_model_serialization(self):
        """Test that Pydantic models can be serialized/deserialized."""
        # Test GenerateRequest
        request = GenerateRequest(
            model="test-model",
            prompt="Test prompt",
            parameters={"temp": 0.7}
        )
        
        request_dict = request.model_dump()
        assert request_dict["model"] == "test-model"
        assert request_dict["prompt"] == "Test prompt"
        assert request_dict["parameters"] == {"temp": 0.7}
        
        # Test GenerateResponse
        response = GenerateResponse(
            response="Test response",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            cost=0.005,
            model="test-model"
        )
        
        response_dict = response.model_dump()
        assert response_dict["response"] == "Test response"
        assert response_dict["prompt_tokens"] == 10
        assert response_dict["model"] == "test-model"
        assert response_dict["error"] is None
