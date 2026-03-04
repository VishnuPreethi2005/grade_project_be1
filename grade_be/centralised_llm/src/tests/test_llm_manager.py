# test_llm_manager.py
import pytest
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, AsyncMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.llm_manager import handle_request, load_llms_from_config, create_llm_instance, container
from src.llm_base import GenerateRequest, GenerateResponse


class TestLLMManager:
    """Test suite for LLM Manager functionality."""

    # ============================================================================
    # CONFIGURATION LOADING TESTS
    # ============================================================================

    @pytest.fixture
    def mock_config_data(self):
        """Mock configuration data for testing."""
        return {
            "openai": {
                "class": "AZUREOpenAILLM",
                "module": "src.llms.Azure_openai_llm",
                "api_key": "",
                "model": "gpt-4.1-nano",
                "temperature": 0.7,
                "max_tokens": 512
            },
            "mistral": {
                "class": "MistralLLM",
                "module": "src.llms.mistral_llm",
                "api_key": "",
                "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
                "temperature": 0.7,
                "max_tokens": 512
            },
            "gemini": {
                "class": "GeminiLLM",
                "module": "src.llms.gemini_llm",
                "api_key": "",
                "model": "gemini-1.5-flash",
                "temperature": 0.7,
                "max_tokens": 512
            }
        }

    def test_load_llms_from_config_valid(self, mock_config_data):
        """Test loading LLMs from valid configuration."""
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config_data))):
            with patch('json.load', return_value=mock_config_data):
                with patch('importlib.import_module') as mock_import:
                    # Mock the module imports
                    mock_openai_module = MagicMock()
                    mock_openai_module.AZUREOpenAILLM = MagicMock()
                    
                    mock_mistral_module = MagicMock()
                    mock_mistral_module.MistralLLM = MagicMock()
                    
                    mock_gemini_module = MagicMock()
                    mock_gemini_module.GeminiLLM = MagicMock()
                    
                    def mock_import_side_effect(module_name):
                        if "Azure_openai_llm" in module_name:
                            return mock_openai_module
                        elif "mistral_llm" in module_name:
                            return mock_mistral_module
                        elif "gemini_llm" in module_name:
                            return mock_gemini_module
                        return MagicMock()
                    
                    mock_import.side_effect = mock_import_side_effect
                    
                    container = load_llms_from_config("fake_config.json")
                    
                    # Verify container has all expected attributes
                    assert hasattr(container, "openai")
                    assert hasattr(container, "mistral")
                    assert hasattr(container, "gemini")

    # ============================================================================
    # LLM INSTANCE CREATION TESTS
    # ============================================================================

    def test_create_llm_instance_success(self):
        """Test successful LLM instance creation."""
        # Mock container with test data
        mock_container_data = {
            'class': MagicMock(),
            'fixed_params': {"api_key": "test-key"},
            'default_params': {"temperature": 0.7, "max_tokens": 512, "model": "test-model"}
        }
        
        # Patch the container to have our test model
        with patch.object(container, 'test_model', mock_container_data, create=True):
            # Mock the hasattr check to return True
            with patch('builtins.hasattr', return_value=True):
                instance = create_llm_instance("test_model", {"temperature": 0.5})
                
                # Verify the class was called with merged parameters
                mock_container_data['class'].assert_called_once_with(
                    api_key="test-key",
                    temperature=0.5,  # Overridden
                    max_tokens=512,   # Default
                    model="test-model"  # Default
                )

    def test_create_llm_instance_unknown_model(self):
        """Test LLM instance creation with unknown model."""
        with pytest.raises(ValueError, match="Unknown model: nonexistent_model"):
            create_llm_instance("nonexistent_model")

    def test_create_llm_instance_no_request_params(self):
        """Test LLM instance creation without request parameters."""
        mock_container_data = {
            'class': MagicMock(),
            'fixed_params': {"api_key": "test-key"},
            'default_params': {"temperature": 0.7, "model": "test-model"}
        }
        
        with patch.object(container, 'test_model', mock_container_data, create=True):
            with patch('builtins.hasattr', return_value=True):
                instance = create_llm_instance("test_model")
                
                # Verify the class was called with default parameters only
                mock_container_data['class'].assert_called_once_with(
                    api_key="test-key",
                    temperature=0.7,
                    model="test-model"
                )

    def test_create_llm_instance_filters_fixed_params(self):
        """Test that fixed parameters cannot be overridden."""
        mock_container_data = {
            'class': MagicMock(),
            'fixed_params': {"api_key": "test-key"},
            'default_params': {"temperature": 0.7, "model": "test-model"}
        }
        
        with patch.object(container, 'test_model', mock_container_data, create=True):
            with patch('builtins.hasattr', return_value=True):
                # Try to override fixed parameters
                instance = create_llm_instance("test_model", {
                    "temperature": 0.5,
                    "api_key": "hacker-key",  # Should be filtered out
                    "class": "HackerClass",  # Should be filtered out
                    "module": "hacker.module"  # Should be filtered out
                })
                
                # Verify fixed parameters weren't overridden
                mock_container_data['class'].assert_called_once_with(
                    api_key="test-key",  # Original fixed param
                    temperature=0.5,     # Allowed override
                    model="test-model"
                )

    # ============================================================================
    # HANDLE REQUEST TESTS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_handle_request_invalid_json(self):
        """Test handle_request with invalid JSON."""
        resp = await handle_request("not a json")
        assert "error" in resp
        assert "Expecting value" in resp["error"] or "JSON" in resp["error"]

    @pytest.mark.asyncio
    async def test_handle_request_single_success(self):
        """Test successful single request handling."""
        # Mock LLM instance
        mock_llm = MagicMock()
        mock_response = GenerateResponse(
            response="Test response",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            cost=0.005,
            model="test-model"
        )
        mock_llm.generate = AsyncMock(return_value=mock_response)
        
        with patch('src.llm_manager.create_llm_instance', return_value=mock_llm):
            with patch('builtins.hasattr', return_value=True):
                request_json = json.dumps({
                    "model": "openai",
                    "prompt": "Test prompt",
                    "parameters": {"temperature": 0.5}
                })
                
                result = await handle_request(request_json)
                
                # Verify the response format - handle_request returns a string for single requests
                assert isinstance(result, str)
                assert "Response:" in result
                assert "Test response" in result

    @pytest.mark.asyncio
    async def test_handle_request_single_with_error(self):
        """Test single request handling with LLM error."""
        # Mock LLM instance that returns error
        mock_llm = MagicMock()
        mock_response = GenerateResponse(
            response="",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost=0.0,
            model="test-model",
            error="API Error occurred"
        )
        mock_llm.generate = AsyncMock(return_value=mock_response)
        
        with patch('src.llm_manager.create_llm_instance', return_value=mock_llm):
            with patch('builtins.hasattr', return_value=True):
                request_json = json.dumps({
                    "model": "openai",
                    "prompt": "Test prompt"
                })
                
                result = await handle_request(request_json)
                
                # Verify error response format
                assert isinstance(result, str)
                assert "Error:" in result
                assert "API Error occurred" in result

    @pytest.mark.asyncio
    async def test_handle_request_single_unknown_model(self):
        """Test single request with unknown model."""
        request_json = json.dumps({
            "model": "unknown_model",
            "prompt": "Test prompt"
        })
        
        result = await handle_request(request_json)
        
        assert "error" in result
        assert "Unknown model: unknown_model" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_request_batch_success(self):
        """Test successful batch request handling."""
        # Mock LLM instance
        mock_llm = MagicMock()
        mock_responses = [
            GenerateResponse(
                response="Response 1",
                prompt_tokens=10,
                completion_tokens=15,
                total_tokens=25,
                cost=0.002,
                model="test-model"
            ),
            GenerateResponse(
                response="Response 2",
                prompt_tokens=12,
                completion_tokens=18,
                total_tokens=30,
                cost=0.003,
                model="test-model"
            )
        ]
        mock_llm.batch_generate = AsyncMock(return_value=mock_responses)
        
        with patch('src.llm_manager.create_llm_instance', return_value=mock_llm):
            with patch('builtins.hasattr', return_value=True):
                batch_json = json.dumps([
                    {
                        "model": "openai",
                        "prompt": "First prompt",
                        "parameters": {"temperature": 0.5}
                    },
                    {
                        "model": "openai",
                        "prompt": "Second prompt",
                        "parameters": {"temperature": 0.5}
                    }
                ])
                
                result = await handle_request(batch_json)
                
                # Verify batch response format
                assert isinstance(result, list)
                assert len(result) == 2
                assert result[0] == "Response 1"
                assert result[1] == "Response 2"

    @pytest.mark.asyncio
    async def test_handle_request_batch_with_errors(self):
        """Test batch request handling with some errors."""
        # Mock LLM instance
        mock_llm = MagicMock()
        mock_responses = [
            GenerateResponse(
                response="Response 1",
                prompt_tokens=10,
                completion_tokens=15,
                total_tokens=25,
                cost=0.002,
                model="test-model"
            ),
            GenerateResponse(
                response="",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                cost=0.0,
                model="test-model",
                error="API Error"
            )
        ]
        mock_llm.batch_generate = AsyncMock(return_value=mock_responses)
        
        with patch('src.llm_manager.create_llm_instance', return_value=mock_llm):
            with patch('builtins.hasattr', return_value=True):
                batch_json = json.dumps([
                    {"model": "openai", "prompt": "First prompt"},
                    {"model": "openai", "prompt": "Second prompt"}
                ])
                
                result = await handle_request(batch_json)
                
                # Verify mixed response format
                assert isinstance(result, list)
                assert len(result) == 2
                assert result[0] == "Response 1"
                assert result[1] == "API Error"  # Error returned directly

    @pytest.mark.asyncio
    async def test_handle_request_empty_batch(self):
        """Test handling of empty batch request."""
        batch_json = json.dumps([])
        
        result = await handle_request(batch_json)
        
        assert "error" in result
        assert "Empty batch request" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_request_batch_unknown_model(self):
        """Test batch request with unknown model."""
        batch_json = json.dumps([
            {"model": "unknown_model", "prompt": "Test prompt"}
        ])
        
        result = await handle_request(batch_json)
        
        assert "error" in result
        assert "Unknown model: unknown_model" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_request_exception_handling(self):
        """Test handle_request exception handling."""
        # Mock create_llm_instance to raise an exception
        with patch('src.llm_manager.create_llm_instance', side_effect=Exception("Test exception")):
            with patch('builtins.hasattr', return_value=True):
                request_json = json.dumps({
                    "model": "openai",
                    "prompt": "Test prompt"
                })
                
                result = await handle_request(request_json)
                
                assert "error" in result
                assert "Test exception" in result["error"]

    # ============================================================================
    # INTEGRATION TESTS
    # ============================================================================

    def test_container_initialization(self):
        """Test that the global container is properly initialized."""
        # This tests the actual container initialization at module level
        # The container should be created when the module is imported
        assert container is not None

    @pytest.mark.asyncio
    async def test_end_to_end_request_flow(self):
        """Test complete end-to-end request flow."""
        # Mock the entire flow
        mock_llm_class = MagicMock()
        mock_llm_instance = MagicMock()
        mock_llm_class.return_value = mock_llm_instance
        
        mock_response = GenerateResponse(
            response="End-to-end response",
            prompt_tokens=20,
            completion_tokens=30,
            total_tokens=50,
            cost=0.01,
            model="test-model"
        )
        mock_llm_instance.generate = AsyncMock(return_value=mock_response)
        
        # Mock container data
        mock_container_data = {
            'class': mock_llm_class,
            'fixed_params': {"api_key": "test-key"},
            'default_params': {"temperature": 0.7, "model": "test-model"}
        }
        
        with patch.object(container, 'test_model', mock_container_data, create=True):
            with patch('builtins.hasattr', return_value=True):
                request_json = json.dumps({
                    "model": "test_model",
                    "prompt": "End-to-end test prompt",
                    "parameters": {"temperature": 0.8, "max_tokens": 100}
                })
                
                result = await handle_request(request_json)
                
                # Verify the complete flow
                mock_llm_class.assert_called_once_with(
                    api_key="test-key",
                    temperature=0.8,  # Overridden
                    model="test-model",
                    max_tokens=100  # New parameter
                )
                
                mock_llm_instance.generate.assert_called_once()
                
                assert "Response:" in result
                assert "End-to-end response" in result
