# src/tests/llm/test_openai_llm.py
import pytest
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, AsyncMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.llms.Azure_openai_llm import AZUREOpenAILLM
from src.llm_base import GenerateRequest, GenerateResponse


class TestAZUREOpenAILLM:
    """Comprehensive test suite for AZUREOpenAILLM class following production standards."""
    
    # Remove any __init__ method if present - pytest doesn't allow it in test classes

    @pytest.fixture
    def mock_pricing_data(self):
        """Mock pricing data for GPT-4.1 Nano only."""
        return {
            "pricing": {
                "OpenAI": {
                    "gpt-4.1-nano": {
                        "input": 0.0001,
                        "output": 0.0004
                    }
                }
            }
        }

    @pytest.fixture
    def azure_openai_instance(self, mock_pricing_data, monkeypatch):
        """Create AZUREOpenAILLM instance with mocked dependencies."""
        # Use monkeypatch for environment variables (recommended by pytest)
        monkeypatch.setenv("OPENAI_API_KEY", "")  # Set empty to avoid env interference
        
        # Mock all the dependencies
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_pricing_data))):
            with patch('json.load', return_value=mock_pricing_data):
                with patch('src.utils.config.get_env', return_value=None):
                    with patch('src.llms.Azure_openai_llm.ChatOpenAI') as mock_chat:
                        with patch('src.llms.Azure_openai_llm.AzureChatOpenAI') as mock_azure:
                            with patch('logging.getLogger'):
                                # Mock the LLM instance
                                mock_llm_instance = MagicMock()
                                mock_chat.return_value = mock_llm_instance
                                mock_azure.return_value = mock_llm_instance
                                
                                return AZUREOpenAILLM(
                                    api_key="test-api-key",
                                    model="gpt-4.1-nano",
                                    temperature=0.7,
                                    max_tokens=512,
                                    top_p=1.0,
                                    n=1,
                                    stop=None,
                                    frequency_penalty=0.0,
                                    presence_penalty=0.0
                                )

    def test_init_with_all_parameters(self, azure_openai_instance):
        """Test initialization with all parameters."""
        # Verify all attributes are set correctly
        assert azure_openai_instance.api_key == "test-api-key"
        assert azure_openai_instance.model == "gpt-4.1-nano"
        assert azure_openai_instance.temperature == 0.7
        assert azure_openai_instance.max_tokens == 512
        assert azure_openai_instance.top_p == 1.0
        assert azure_openai_instance.n == 1
        assert azure_openai_instance.stop is None
        assert azure_openai_instance.frequency_penalty == 0.0
        assert azure_openai_instance.presence_penalty == 0.0
        # Verify pricing data was loaded
        assert hasattr(azure_openai_instance, 'pricing_data')
        # Verify LLM was configured
        assert hasattr(azure_openai_instance, 'llm')

    def test_init_with_env_api_key(self, mock_pricing_data, monkeypatch):
        """Test initialization with API key from environment."""
        # Use monkeypatch to set environment variable
        monkeypatch.setenv("OPENAI_API_KEY", "env-api-key")
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_pricing_data))):
            with patch('json.load', return_value=mock_pricing_data):
                with patch('src.utils.config.get_env', return_value="env-api-key"):
                    with patch('src.llms.Azure_openai_llm.ChatOpenAI') as mock_chat:
                        with patch('logging.getLogger'):
                            mock_chat.return_value = MagicMock()
                            
                            # Create instance
                            llm = AZUREOpenAILLM(api_key="fallback-key", model="gpt-4.1-nano")
                            
                            # Verify environment API key is used
                            assert llm.api_key == "env-api-key"

    def test_configure_llm_standard_openai(self, mock_pricing_data, monkeypatch):
        """Test LLM configuration for standard OpenAI."""
        # Clear any environment variables
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_pricing_data))):
            with patch('json.load', return_value=mock_pricing_data):
                with patch('src.utils.config.get_env', return_value=None):
                    with patch('src.llms.Azure_openai_llm.ChatOpenAI') as mock_chat:
                        with patch('logging.getLogger'):
                            mock_llm_instance = MagicMock()
                            mock_chat.return_value = mock_llm_instance
                            
                            # Create instance with short API key (triggers standard OpenAI)
                            llm = AZUREOpenAILLM(
                                api_key="short-key",  # Less than 40 characters
                                model="gpt-4.1-nano",
                                temperature=0.5,
                                max_tokens=256,
                                top_p=0.9,
                                n=1,
                                frequency_penalty=0.1,
                                presence_penalty=0.2
                            )
                            
                            # Verify ChatOpenAI was called with correct parameters
                            mock_chat.assert_called_once_with(
                                api_key="short-key",
                                model="gpt-4.1-nano",
                                temperature=0.5,
                                max_tokens=256,
                                top_p=0.9,
                                n=1,
                                frequency_penalty=0.1,
                                presence_penalty=0.2
                            )

    def test_calculate_cost_success(self, azure_openai_instance):
        """Test successful cost calculation."""
        class MockCallback:
            prompt_tokens = 100
            completion_tokens = 50
        
        cb = MockCallback()
        cost = azure_openai_instance._calculate_cost(cb)
        
        expected_cost = (100 * 0.0001 / 1000) + (50 * 0.0004 / 1000)
        assert cost == expected_cost

    @pytest.fixture
    def sample_request(self):
        """Sample GenerateRequest for testing."""
        return GenerateRequest(
            model="gpt-4.1-nano",
            prompt="What is artificial intelligence?",
            parameters={"temperature": 0.5, "max_tokens": 100}
        )

    def test_handle_error_401_invalid_authentication(self, azure_openai_instance, sample_request):
        """Test error handling for 401 invalid authentication."""
        error = Exception("401 invalid authentication")
        result = azure_openai_instance.handle_error(error, sample_request)
        
        assert result.error == "Invalid Authentication: Ensure the correct API key and requesting organization are being used."
        assert result.response == ""
        assert result.cost == 0.0
        assert result.model == "gpt-4.1-nano"

    @pytest.mark.asyncio
    @patch('src.llms.Azure_openai_llm.get_openai_callback')
    @patch('src.llms.Azure_openai_llm.mlflow')
    async def test_generate_success(self, mock_mlflow, mock_callback, azure_openai_instance, sample_request):
        """Test successful single generation."""
        class MockResponse:
            content = "Artificial intelligence is a branch of computer science..."
        
        class MockCallbackObj:
            prompt_tokens = 25
            completion_tokens = 75
            total_tokens = 100
        
        # Setup callback mock
        mock_cb = MockCallbackObj()
        mock_callback.return_value.__enter__.return_value = mock_cb
        mock_callback.return_value.__exit__.return_value = None
        
        # Setup MLflow mock
        mock_mlflow.start_run.return_value.__enter__ = MagicMock()
        mock_mlflow.start_run.return_value.__exit__ = MagicMock()
        
        # Setup LLM mock
        azure_openai_instance.llm.ainvoke = AsyncMock(return_value=MockResponse())
        
        # Execute
        result = await azure_openai_instance.generate(sample_request)
        
        # Verify
        assert result.response == "Artificial intelligence is a branch of computer science..."
        assert result.prompt_tokens == 25
        assert result.completion_tokens == 75
        assert result.total_tokens == 100
        assert result.model == "gpt-4.1-nano"
        assert result.error is None
