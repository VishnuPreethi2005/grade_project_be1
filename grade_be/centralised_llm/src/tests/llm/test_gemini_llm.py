# test_gemini_llm.py
import pytest
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, AsyncMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.llms.gemini_llm import GeminiLLM
from src.llm_base import GenerateRequest, GenerateResponse


class TestGeminiLLM:
    """Comprehensive test suite for GeminiLLM class following production standards."""

    # ============================================================================
    # FIXTURES
    # ============================================================================
    
    @pytest.fixture
    def mock_pricing_data(self):
        """Mock pricing data for Gemini models."""
        return {
            "pricing": {
                "Gemini": {
                    "gemini-1.5-flash": {
                        "input": 0.00013,
                        "output": 0.0005
                    }
                }
            }
        }

    @pytest.fixture
    def gemini_instance(self, mock_pricing_data, monkeypatch):
        """Create GeminiLLM instance with mocked dependencies."""
        # Clear environment variables
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_pricing_data))):
            with patch('json.load', return_value=mock_pricing_data):
                with patch('src.llms.gemini_llm.get_env', return_value=None):
                    with patch('google.generativeai.configure'):
                        with patch('google.generativeai.GenerativeModel') as mock_model:
                            with patch('logging.getLogger'):
                                mock_model_instance = MagicMock()
                                mock_model.return_value = mock_model_instance
                                
                                return GeminiLLM(
                                    api_key="test-api-key",
                                    model="gemini-1.5-flash",
                                    temperature=0.7,
                                    max_tokens=512,
                                    top_p=0.9,
                                    top_k=40,
                                    n=1,
                                    stop_sequences=None,
                                    max_retries=2,
                                    timeout=None,
                                    safety_settings=None,
                                    system_instruction=None
                                )

    @pytest.fixture
    def sample_request(self):
        """Sample GenerateRequest for testing."""
        return GenerateRequest(
            model="gemini-1.5-flash",
            prompt="What is artificial intelligence?",
            parameters={"temperature": 0.5, "max_tokens": 100}
        )

    @pytest.fixture
    def sample_batch_requests(self):
        """Sample batch requests for testing."""
        return [
            GenerateRequest(
                model="gemini-1.5-flash",
                prompt="Explain machine learning",
                parameters={"temperature": 0.3}
            ),
            GenerateRequest(
                model="gemini-1.5-flash",
                prompt="What is deep learning?",
                parameters={"temperature": 0.7}
            )
        ]

    # ============================================================================
    # INITIALIZATION TESTS
    # ============================================================================
    
    def test_init_with_all_parameters(self, gemini_instance):
        """Test initialization with all parameters."""
        assert gemini_instance.api_key == "test-api-key"
        assert gemini_instance.model == "gemini-1.5-flash"
        assert gemini_instance.temperature == 0.7
        assert gemini_instance.max_tokens == 512
        assert gemini_instance.top_p == 0.9
        assert gemini_instance.top_k == 40
        assert gemini_instance.n == 1
        assert gemini_instance.stop_sequences is None
        assert gemini_instance.max_retries == 2
        assert gemini_instance.timeout is None
        assert gemini_instance.safety_settings == {}
        assert gemini_instance.system_instruction is None

    def test_init_with_env_api_key(self, mock_pricing_data, monkeypatch):
        """Test initialization with API key from environment."""
        # Set environment variable using monkeypatch
        monkeypatch.setenv("GOOGLE_API_KEY", "env-api-key")
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_pricing_data))):
            with patch('json.load', return_value=mock_pricing_data):
                with patch('src.llms.gemini_llm.get_env', return_value="env-api-key"):
                    with patch('google.generativeai.configure'):
                        with patch('google.generativeai.GenerativeModel'):
                            with patch('logging.getLogger'):
                                llm = GeminiLLM(api_key="fallback-key", model="gemini-1.5-flash")
                                assert llm.api_key == "env-api-key"

    def test_init_without_api_key_raises_error(self, mock_pricing_data, monkeypatch):
        """Test initialization without API key raises ValueError."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_pricing_data))):
            with patch('json.load', return_value=mock_pricing_data):
                with patch('src.llms.gemini_llm.get_env', return_value=None):
                    with pytest.raises(ValueError, match="Google API key is required"):
                        GeminiLLM(api_key=None, model="gemini-1.5-flash")

    def test_init_with_custom_safety_settings(self, mock_pricing_data, monkeypatch):
        """Test initialization with custom safety settings."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        safety_settings = {"HARM_CATEGORY_HARASSMENT": "BLOCK_NONE"}
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_pricing_data))):
            with patch('json.load', return_value=mock_pricing_data):
                with patch('src.llms.gemini_llm.get_env', return_value=None):
                    with patch('google.generativeai.configure'):
                        with patch('google.generativeai.GenerativeModel'):
                            with patch('logging.getLogger'):
                                llm = GeminiLLM(
                                    api_key="test-key",
                                    model="gemini-1.5-flash",
                                    safety_settings=safety_settings
                                )
                                assert llm.safety_settings == safety_settings

    # ============================================================================
    # PRICING DATA LOADING TESTS
    # ============================================================================
    
    def test_load_pricing_data_success(self, mock_pricing_data):
        """Test successful loading of pricing data."""
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_pricing_data))):
            with patch('json.load', return_value=mock_pricing_data):
                with patch('src.llms.gemini_llm.get_env', return_value=None):
                    with patch('google.generativeai.configure'):
                        with patch('google.generativeai.GenerativeModel'):
                            with patch('logging.getLogger'):
                                llm = GeminiLLM(api_key="test", model="gemini-1.5-flash")
                                assert llm.pricing_data == mock_pricing_data["pricing"]["Gemini"]

    @patch('src.llms.gemini_llm.logger')
    def test_load_pricing_data_file_not_found(self, mock_logger):
        """Test pricing data loading when file is not found."""
        with patch('builtins.open', side_effect=FileNotFoundError("File not found")):
            with patch('src.llms.gemini_llm.get_env', return_value=None):
                with patch('google.generativeai.configure'):
                    with patch('google.generativeai.GenerativeModel'):
                        with patch('logging.getLogger'):
                            llm = GeminiLLM(api_key="test", model="gemini-1.5-flash")
                            assert llm.pricing_data == {}
                            mock_logger.error.assert_called_once()

    # ============================================================================
    # MODEL CONFIGURATION TESTS
    # ============================================================================
    
    @patch('google.generativeai.GenerativeModel')
    def test_configure_model_with_all_parameters(self, mock_generative_model, mock_pricing_data, monkeypatch):
        """Test model configuration with all parameters."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_pricing_data))):
            with patch('json.load', return_value=mock_pricing_data):
                with patch('src.llms.gemini_llm.get_env', return_value=None):
                    with patch('google.generativeai.configure'):
                        with patch('logging.getLogger'):
                            llm = GeminiLLM(
                                api_key="test-key",
                                model="gemini-1.5-flash",
                                temperature=0.5,
                                max_tokens=256,
                                top_p=0.8,
                                top_k=30,
                                stop_sequences=["END", "STOP"],
                                system_instruction="You are a helpful assistant"
                            )
                            
                            # Verify GenerativeModel was called with correct parameters
                            mock_generative_model.assert_called_once_with(
                                model_name="gemini-1.5-flash",
                                generation_config={
                                    "temperature": 0.5,
                                    "max_output_tokens": 256,
                                    "top_p": 0.8,
                                    "top_k": 30,
                                    "stop_sequences": ["END", "STOP"]
                                },
                                safety_settings={},
                                system_instruction="You are a helpful assistant"
                            )

    # ============================================================================
    # COST CALCULATION TESTS
    # ============================================================================
    
    def test_calculate_cost_success(self, gemini_instance):
        """Test successful cost calculation."""
        cost = gemini_instance._calculate_cost(100, 50)
        
        # Expected: (100 * 0.00013 / 1000) + (50 * 0.0005 / 1000) = 0.000038
        expected_cost = (100 * 0.00013 / 1000) + (50 * 0.0005 / 1000)
        assert cost == expected_cost

    def test_calculate_cost_zero_tokens(self, gemini_instance):
        """Test cost calculation with zero tokens."""
        cost = gemini_instance._calculate_cost(0, 0)
        assert cost == 0.0

    def test_calculate_cost_missing_pricing_data(self, gemini_instance):
        """Test cost calculation with missing pricing data."""
        gemini_instance.pricing_data = {}
        
        cost = gemini_instance._calculate_cost(100, 50)
        
        assert cost == 0.0
        # Note: If your implementation doesn't log warnings, this test just verifies graceful handling

    # ============================================================================
    # ERROR HANDLING TESTS
    # ============================================================================
    
    def test_handle_error_400_invalid_argument(self, gemini_instance, sample_request):
        """Test error handling for 400 invalid argument."""
        error = Exception("400 invalid_argument: The request body is malformed")
        result = gemini_instance.handle_error(error, sample_request)
        
        assert result.error == "Invalid Argument: The request body is malformed. Check the API reference for request format."
        assert result.response == ""
        assert result.cost == 0.0
        assert result.model == "gemini-1.5-flash"

    def test_handle_error_403_permission_denied(self, gemini_instance, sample_request):
        """Test error handling for 403 permission denied."""
        error = Exception("403 permission_denied: API key doesn't have permissions")
        result = gemini_instance.handle_error(error, sample_request)
        
        assert "Permission Denied" in result.error

    def test_handle_error_429_resource_exhausted(self, gemini_instance, sample_request):
        """Test error handling for 429 resource exhausted."""
        error = Exception("429 resource_exhausted: Rate limit exceeded")
        result = gemini_instance.handle_error(error, sample_request)
        
        assert "Resource Exhausted" in result.error

    def test_handle_error_500_internal_error(self, gemini_instance, sample_request):
        """Test error handling for 500 internal error."""
        error = Exception("500 internal error occurred")
        result = gemini_instance.handle_error(error, sample_request)
        
        assert "Internal Error" in result.error

    def test_handle_error_generic_error(self, gemini_instance, sample_request):
        """Test error handling for generic errors."""
        error = Exception("Unknown error occurred")
        result = gemini_instance.handle_error(error, sample_request)
        
        assert "Gemini API Error: Unknown error occurred" in result.error

    # ============================================================================
    # TOKEN USAGE EXTRACTION TESTS
    # ============================================================================
    
    def test_extract_token_usage_with_usage_metadata(self, gemini_instance):
        """Test token usage extraction with usage metadata."""
        class MockUsageMetadata:
            prompt_token_count = 25
            candidates_token_count = 75
            total_token_count = 100
        
        class MockResponse:
            usage_metadata = MockUsageMetadata()
        
        response = MockResponse()
        prompt_tokens, completion_tokens, total_tokens = gemini_instance._extract_token_usage(response)
        
        assert prompt_tokens == 25
        assert completion_tokens == 75
        assert total_tokens == 100

    def test_extract_token_usage_fallback_estimation(self, gemini_instance):
        """Test token usage extraction with fallback estimation."""
        class MockResponse:
            text = "This is a test response with some content"
        
        response = MockResponse()
        prompt_tokens, completion_tokens, total_tokens = gemini_instance._extract_token_usage(response)
        
        assert prompt_tokens == 0
        assert completion_tokens > 0  # Should estimate based on text length
        assert total_tokens == completion_tokens

    def test_extract_token_usage_no_data(self, gemini_instance):
        """Test token usage extraction with no data."""
        class MockResponse:
            pass
        
        response = MockResponse()
        prompt_tokens, completion_tokens, total_tokens = gemini_instance._extract_token_usage(response)
        
        assert prompt_tokens == 0
        assert completion_tokens == 0
        assert total_tokens == 0

    # ============================================================================
    # CALLBACK TESTS
    # ============================================================================
    
    def test_get_callback_params(self, gemini_instance):
        """Test get_callback_params method."""
        params = gemini_instance.get_callback_params()
        
        assert isinstance(params, dict)
        assert params["model"] == "gemini-1.5-flash"
        assert params["temperature"] == 0.7
        assert params["max_tokens"] == 512
        assert params["top_p"] == 0.9
        assert params["top_k"] == 40

    # ============================================================================
    # SINGLE GENERATION TESTS
    # ============================================================================
    
    @pytest.mark.asyncio
    @patch('src.llms.gemini_llm.mlflow')
    async def test_generate_success(self, mock_mlflow, gemini_instance, sample_request):
        """Test successful single generation."""
        # Mock response
        class MockUsageMetadata:
            prompt_token_count = 25
            candidates_token_count = 75
            total_token_count = 100
        
        class MockResponse:
            text = "Artificial intelligence is a branch of computer science..."
            usage_metadata = MockUsageMetadata()
        
        # Setup mocks
        mock_mlflow.start_run.return_value.__enter__ = MagicMock()
        mock_mlflow.start_run.return_value.__exit__ = MagicMock()
        
        gemini_instance.genai_model.generate_content_async = AsyncMock(return_value=MockResponse())
        
        # Execute
        result = await gemini_instance.generate(sample_request)
        
        # Verify
        gemini_instance.genai_model.generate_content_async.assert_called_once()
        
        assert result.response == "Artificial intelligence is a branch of computer science..."
        assert result.prompt_tokens == 25
        assert result.completion_tokens == 75
        assert result.total_tokens == 100
        assert result.model == "gemini-1.5-flash"
        assert result.error is None
        assert result.cost > 0

    @pytest.mark.asyncio
    async def test_generate_blocked_content(self, gemini_instance, sample_request):
        """Test generation with blocked content."""
        # Mock blocked response
        class MockPromptFeedback:
            block_reason = "SAFETY"
        
        class MockResponse:
            text = ""
            prompt_feedback = MockPromptFeedback()
        
        gemini_instance.genai_model.generate_content_async = AsyncMock(return_value=MockResponse())
        
        result = await gemini_instance.generate(sample_request)
        
        assert result.response == ""
        assert result.error == "Content blocked: SAFETY"
        assert result.cost == 0.0

    @pytest.mark.asyncio
    async def test_generate_api_exception(self, gemini_instance, sample_request):
        """Test generation with API exception."""
        gemini_instance.genai_model.generate_content_async = AsyncMock(
            side_effect=Exception("API connection timeout")
        )
        
        result = await gemini_instance.generate(sample_request)
        
        assert result.response == ""
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
        assert result.total_tokens == 0
        assert result.cost == 0.0
        assert result.model == "gemini-1.5-flash"
        # The error message is processed by handle_error method
        assert "Request Timeout" in result.error or "API connection timeout" in result.error

    # ============================================================================
    # BATCH GENERATION TESTS
    # ============================================================================
    
    @pytest.mark.asyncio
    @patch('src.llms.gemini_llm.mlflow')
    async def test_batch_generate_success(self, mock_mlflow, gemini_instance, sample_batch_requests):
        """Test successful batch generation."""
        # Mock responses
        class MockUsageMetadata:
            def __init__(self, prompt_tokens, completion_tokens):
                self.prompt_token_count = prompt_tokens
                self.candidates_token_count = completion_tokens
                self.total_token_count = prompt_tokens + completion_tokens
        
        class MockResponse:
            def __init__(self, text, prompt_tokens, completion_tokens):
                self.text = text
                self.usage_metadata = MockUsageMetadata(prompt_tokens, completion_tokens)
        
        mock_responses = [
            MockResponse("Machine learning is a subset of AI...", 15, 35),
            MockResponse("Deep learning uses neural networks...", 18, 42)
        ]
        
        # Setup mocks
        mock_mlflow.start_run.return_value.__enter__ = MagicMock()
        mock_mlflow.start_run.return_value.__exit__ = MagicMock()
        
        # Mock the async method to return different responses for each call
        gemini_instance.genai_model.generate_content_async = AsyncMock(side_effect=mock_responses)
        
        # Execute
        results = await gemini_instance.batch_generate(sample_batch_requests)
        
        # Verify results
        assert len(results) == 2
        assert results[0].response == "Machine learning is a subset of AI..."
        assert results[1].response == "Deep learning uses neural networks..."
        assert results[0].prompt_tokens == 15
        assert results[0].completion_tokens == 35
        assert results[1].prompt_tokens == 18
        assert results[1].completion_tokens == 42

    @pytest.mark.asyncio
    async def test_batch_generate_with_exceptions(self, gemini_instance, sample_batch_requests):
        """Test batch generation with some exceptions."""
        # Mock one success and one exception
        class MockResponse:
            text = "Successful response"
            usage_metadata = MagicMock()
            usage_metadata.prompt_token_count = 10
            usage_metadata.candidates_token_count = 20
            usage_metadata.total_token_count = 30
        
        def side_effect(*args, **kwargs):
            # First call succeeds, second call fails
            if not hasattr(side_effect, 'call_count'):
                side_effect.call_count = 0
            side_effect.call_count += 1
            
            if side_effect.call_count == 1:
                return MockResponse()
            else:
                raise Exception("API Error")
        
        gemini_instance.genai_model.generate_content_async = AsyncMock(side_effect=side_effect)
        
        results = await gemini_instance.batch_generate(sample_batch_requests)
        
        # Verify mixed results
        assert len(results) == 2
        assert results[0].response == "Successful response"
        assert results[0].error is None
        assert results[1].response == ""
        assert "API Error" in results[1].error or "Gemini API Error" in results[1].error

    @pytest.mark.asyncio
    async def test_batch_generate_empty_requests(self, gemini_instance):
        """Test batch generation with empty request list."""
        results = await gemini_instance.batch_generate([])
        assert results == []

    # ============================================================================
    # SYNCHRONOUS METHODS TESTS
    # ============================================================================
    
    @patch('src.llms.gemini_llm.mlflow')
    def test_generate_sync_success(self, mock_mlflow, gemini_instance, sample_request):
        """Test successful synchronous generation."""
        # Mock response
        class MockResponse:
            text = "Sync response"
            usage_metadata = MagicMock()
            usage_metadata.prompt_token_count = 10
            usage_metadata.candidates_token_count = 20
            usage_metadata.total_token_count = 30
        
        # Setup mocks
        mock_mlflow.start_run.return_value.__enter__ = MagicMock()
        mock_mlflow.start_run.return_value.__exit__ = MagicMock()
        
        gemini_instance.genai_model.generate_content = MagicMock(return_value=MockResponse())
        
        result = gemini_instance.generate_sync(sample_request)
        
        assert result.response == "Sync response"
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 20
        assert result.total_tokens == 30

    def test_batch_generate_sync_success(self, gemini_instance, sample_batch_requests):
        """Test successful synchronous batch generation."""
        # Mock the sync generate method
        def mock_generate_sync(request):
            return GenerateResponse(
                response=f"Sync response for: {request.prompt}",
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                cost=0.001,
                model="gemini-1.5-flash"
            )
        
        gemini_instance.generate_sync = MagicMock(side_effect=mock_generate_sync)
        
        results = gemini_instance.batch_generate_sync(sample_batch_requests)
        
        assert len(results) == 2
        assert "Explain machine learning" in results[0].response
        assert "What is deep learning" in results[1].response

    # ============================================================================
    # PROMPT PREPARATION TESTS
    # ============================================================================
    
    def test_prepare_prompt_simple(self, gemini_instance):
        """Test simple prompt preparation."""
        prompt = "What is AI?"
        result = gemini_instance._prepare_prompt(prompt)
        assert result == "What is AI?"

    def test_prepare_prompt_with_system_message_convert_true(self, mock_pricing_data, monkeypatch):
        """Test prompt preparation with system message conversion enabled."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_pricing_data))):
            with patch('json.load', return_value=mock_pricing_data):
                with patch('src.llms.gemini_llm.get_env', return_value=None):
                    with patch('google.generativeai.configure'):
                        with patch('google.generativeai.GenerativeModel'):
                            with patch('logging.getLogger'):
                                llm = GeminiLLM(
                                    api_key="test-key",
                                    model="gemini-1.5-flash",
                                    convert_system_message_to_human=True
                                )
                                
                                result = llm._prepare_prompt("What is AI?", "You are helpful")
                                assert result == "System: You are helpful\n\nUser: What is AI?"

    # ============================================================================
    # MLFLOW LOGGING TESTS
    # ============================================================================
    
    @patch('src.llms.gemini_llm.mlflow')
    def test_log_to_mlflow_complete(self, mock_mlflow, gemini_instance, sample_request):
        """Test complete MLflow logging functionality."""
        # Mock MLflow context manager
        mock_mlflow.start_run.return_value.__enter__ = MagicMock()
        mock_mlflow.start_run.return_value.__exit__ = MagicMock()
        
        class MockResponse:
            text = "Test response"
        
        response = MockResponse()
        cost = 0.0089
        
        gemini_instance._log_to_mlflow(sample_request, response, cost, 45, 85, 130)
        
        # Verify parameter logging
        mock_mlflow.log_params.assert_called_once_with({
            "model": "gemini-1.5-flash",
            "temperature": 0.7,
            "max_tokens": 512,
            "top_p": 0.9,
            "top_k": 40,
            "n": 1,
            "max_retries": 2,
            "timeout": None
        })
        
        # Verify metrics logging
        mock_mlflow.log_metrics.assert_called_once_with({
            "prompt_tokens": 45,
            "completion_tokens": 85,
            "total_tokens": 130,
            "cost": 0.0089
        })
        
        # Verify prompt logging
        mock_mlflow.log_text.assert_called_once_with(
            "What is artificial intelligence?", 
            "prompt.txt"
        )

    @patch('src.llms.gemini_llm.mlflow')
    @patch('src.llms.gemini_llm.logger')
    def test_log_to_mlflow_exception_handling(self, mock_logger, mock_mlflow, gemini_instance, sample_request):
        """Test MLflow logging exception handling."""
        # Mock MLflow to raise exception
        mock_mlflow.start_run.side_effect = Exception("MLflow error")
        
        class MockResponse:
            text = "Test response"
        
        response = MockResponse()
        
        # Should not raise exception, just log warning
        gemini_instance._log_to_mlflow(sample_request, response, 0.001, 10, 20, 30)
        
        mock_logger.warning.assert_called_once()
