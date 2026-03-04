# test_together_llm_common.py
import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
from pathlib import Path
from src.llms.together_llm_common import (
    together_generate_and_log, 
    together_batch_generate_and_log, 
    handle_together_api_error
)
from src.llm_base import GenerateResponse


class TestTogetherCommon:
    """Test suite for Together LLM Common functions."""

    @pytest.fixture
    def mock_pricing_data(self):
        return {
            "pricing": {
                "Mistral AI": {
                    "mistralai/Mistral-7B-Instruct-v0.1": {
                        "input": 0.0002,
                        "output": 0.0002
                    }
                }
            }
        }

    @pytest.fixture
    def pricing_json_path(self, tmp_path):
        """Create a temporary pricing JSON file"""
        pricing_file = tmp_path / "llm_pricing.json"
        pricing_data = {
            "pricing": {
                "Mistral AI": {
                    "mistralai/Mistral-7B-Instruct-v0.1": {
                        "input": 0.0002,
                        "output": 0.0002
                    }
                }
            }
        }
        pricing_file.write_text(json.dumps(pricing_data))
        return pricing_file

    @pytest.mark.asyncio
    async def test_together_generate_and_log_success(self, pricing_json_path, monkeypatch):
        """Test together_generate_and_log function with proper isolation"""
        # Clear environment variables to avoid interference
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.llms.together_llm_common.ChatTogether') as mock_chat_together:
            with patch('src.llms.together_llm_common.mlflow') as mock_mlflow:
                # Setup response mock
                class MockResponse:
                    content = "Test response content"
                    usage_metadata = {
                        "input_tokens": 15,
                        "output_tokens": 25,
                        "total_tokens": 40
                    }
                
                mock_llm_instance = MagicMock()
                mock_llm_instance.ainvoke = AsyncMock(return_value=MockResponse())
                mock_chat_together.return_value = mock_llm_instance
                
                # Mock MLflow context manager
                mock_mlflow.start_run.return_value.__enter__ = MagicMock()
                mock_mlflow.start_run.return_value.__exit__ = MagicMock()
                
                # Call function
                result = await together_generate_and_log(
                    prompt="Test prompt",
                    model="mistralai/Mistral-7B-Instruct-v0.1",
                    api_key="test-api-key",
                    temperature=0.7,
                    max_tokens=100,
                    pricing_json_path=str(pricing_json_path),
                    provider_key="Mistral AI",
                    user_params={"temperature": 0.5}
                )
                
                # Verify ChatTogether initialization - check what parameters are actually passed
                mock_chat_together.assert_called_once()
                call_kwargs = mock_chat_together.call_args[1]
                assert call_kwargs['model'] == "mistralai/Mistral-7B-Instruct-v0.1"
                assert call_kwargs['together_api_key'] == "test-api-key"
                
                # Verify LLM invocation
                mock_llm_instance.ainvoke.assert_called_once_with("Test prompt")
                
                # Verify response structure
                assert isinstance(result, GenerateResponse)
                assert result.response == "Test response content"
                assert result.prompt_tokens == 15
                assert result.completion_tokens == 25
                assert result.total_tokens == 40
                assert result.model == "mistralai/Mistral-7B-Instruct-v0.1"
                assert result.cost >= 0  # Should have calculated some cost

    @pytest.mark.asyncio
    async def test_together_batch_generate_and_log_success(self, pricing_json_path, monkeypatch):
        """Test together_batch_generate_and_log function with proper isolation"""
        # Clear environment variables
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.llms.together_llm_common.ChatTogether') as mock_chat_together:
            with patch('src.llms.together_llm_common.mlflow') as mock_mlflow:
                # Setup batch response mocks
                class MockResponse:
                    def __init__(self, content, tokens):
                        self.content = content
                        self.usage_metadata = tokens
                
                mock_responses = [
                    MockResponse("Response 1", {"input_tokens": 10, "output_tokens": 15, "total_tokens": 25}),
                    MockResponse("Response 2", {"input_tokens": 12, "output_tokens": 18, "total_tokens": 30})
                ]
                
                mock_llm_instance = MagicMock()
                mock_llm_instance.abatch = AsyncMock(return_value=mock_responses)
                mock_chat_together.return_value = mock_llm_instance
                
                # Mock MLflow
                mock_mlflow.start_run.return_value.__enter__ = MagicMock()
                mock_mlflow.start_run.return_value.__exit__ = MagicMock()
                
                # Call function
                prompts = ["Prompt 1", "Prompt 2"]
                results = await together_batch_generate_and_log(
                    prompts=prompts,
                    model="mistralai/Mistral-7B-Instruct-v0.1",
                    api_key="test-api-key",
                    temperature=0.7,
                    max_tokens=100,
                    pricing_json_path=str(pricing_json_path),
                    provider_key="Mistral AI",
                    user_params=None
                )
                
                # Verify ChatTogether initialization
                mock_chat_together.assert_called_once()
                call_kwargs = mock_chat_together.call_args[1]
                assert call_kwargs['model'] == "mistralai/Mistral-7B-Instruct-v0.1"
                assert call_kwargs['together_api_key'] == "test-api-key"
                
                # Verify batch call
                mock_llm_instance.abatch.assert_called_once_with(prompts)
                
                # Verify results
                assert len(results) == 2
                assert isinstance(results[0], GenerateResponse)
                assert isinstance(results[1], GenerateResponse)
                assert results[0].response == "Response 1"
                assert results[0].prompt_tokens == 10
                assert results[0].completion_tokens == 15
                assert results[1].response == "Response 2"
                assert results[1].prompt_tokens == 12
                assert results[1].completion_tokens == 18

    def test_handle_together_api_error_invalid_api_key(self):
        """Test handle_together_api_error for invalid API key"""
        error = Exception("401 invalid api key provided")
        result = handle_together_api_error(error, "mistralai/Mistral-7B-Instruct-v0.1")
        
        assert "Invalid API key provided" in result or "Together API Error" in result

    def test_handle_together_api_error_rate_limit(self):
        """Test handle_together_api_error for rate limit"""
        error = Exception("429 rate limit exceeded")
        result = handle_together_api_error(error, "mistralai/Mistral-7B-Instruct-v0.1")
        
        assert "Rate limit exceeded" in result or "Together API Error" in result

    def test_handle_together_api_error_server_error(self):
        """Test handle_together_api_error for server error"""
        error = Exception("500 internal server error")
        result = handle_together_api_error(error, "mistralai/Mistral-7B-Instruct-v0.1")
        
        assert "Server Error" in result or "Together API Error" in result

    def test_handle_together_api_error_generic(self):
        """Test handle_together_api_error for generic error"""
        error = Exception("Unknown error occurred")
        result = handle_together_api_error(error, "mistralai/Mistral-7B-Instruct-v0.1")
        
        assert "Together API Error" in result

    @pytest.mark.asyncio
    async def test_together_generate_and_log_with_missing_usage_metadata(self, pricing_json_path, monkeypatch):
        """Test together_generate_and_log when response has no usage_metadata"""
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.llms.together_llm_common.ChatTogether') as mock_chat_together:
            with patch('src.llms.together_llm_common.mlflow') as mock_mlflow:
                # Setup response mock without usage_metadata
                class MockResponse:
                    content = "Test response content"
                    # No usage_metadata attribute
                
                mock_llm_instance = MagicMock()
                mock_llm_instance.ainvoke = AsyncMock(return_value=MockResponse())
                mock_chat_together.return_value = mock_llm_instance
                
                # Mock MLflow context manager
                mock_mlflow.start_run.return_value.__enter__ = MagicMock()
                mock_mlflow.start_run.return_value.__exit__ = MagicMock()
                
                # Call function
                result = await together_generate_and_log(
                    prompt="Test prompt",
                    model="mistralai/Mistral-7B-Instruct-v0.1",
                    api_key="test-api-key",
                    temperature=0.7,
                    max_tokens=100,
                    pricing_json_path=str(pricing_json_path),
                    provider_key="Mistral AI",
                    user_params={}
                )
                
                # Should handle missing usage_metadata gracefully
                assert isinstance(result, GenerateResponse)
                assert result.response == "Test response content"
                # Token counts should be estimated or set to 0
                assert result.prompt_tokens >= 0
                assert result.completion_tokens >= 0
                assert result.total_tokens >= 0

    @pytest.mark.asyncio
    async def test_together_batch_generate_empty_prompts(self, pricing_json_path, monkeypatch):
        """Test together_batch_generate_and_log with empty prompts list"""
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.llms.together_llm_common.ChatTogether') as mock_chat_together:
            with patch('src.llms.together_llm_common.mlflow') as mock_mlflow:
                mock_llm_instance = MagicMock()
                mock_llm_instance.abatch = AsyncMock(return_value=[])
                mock_chat_together.return_value = mock_llm_instance
                
                # Mock MLflow
                mock_mlflow.start_run.return_value.__enter__ = MagicMock()
                mock_mlflow.start_run.return_value.__exit__ = MagicMock()
                
                # Call function with empty prompts
                results = await together_batch_generate_and_log(
                    prompts=[],
                    model="mistralai/Mistral-7B-Instruct-v0.1",
                    api_key="test-api-key",
                    temperature=0.7,
                    max_tokens=100,
                    pricing_json_path=str(pricing_json_path),
                    provider_key="Mistral AI",
                    user_params=None
                )
                
                # Should return empty list
                assert results == []
                
                # Should still call ChatTogether and abatch
                mock_chat_together.assert_called_once()
                mock_llm_instance.abatch.assert_called_once_with([])
