# test_metallama_llm.py
import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from src.llms.Metallama_llm import MetaLlamaLLM
from src.llm_base import GenerateRequest, GenerateResponse


class TestMetaLlamaLLM:
    """Test suite for MetaLlamaLLM class."""

    def test_init(self, monkeypatch):
        """Test MetaLlamaLLM initialization with monkeypatch for env vars."""
        # Use monkeypatch to clear environment variables
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.utils.config.get_env', return_value=None):
            llm = MetaLlamaLLM(
                api_key="test-api-key",
                model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                temperature=0.7,
                max_tokens=512
            )
            
            assert llm.api_key == "test-api-key"
            assert llm.model == "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
            assert llm.temperature == 0.7
            assert llm.max_tokens == 512
            assert llm.stop == ["</s>", "<|eot_id|>"]
            assert llm.top_p == 0.7
            assert llm.top_k == 50
            assert llm.repetition_penalty == 1.0
            assert llm.stream_tokens == False
            assert llm.safety_model is None
            assert llm.n == 1
            assert llm.provider_key == "Meta Llama"
            assert isinstance(llm.pricing_json_path, Path)
            assert llm.pricing_json_path.name == "llm_pricing.json"

    @pytest.mark.asyncio
    @patch('src.llms.Metallama_llm.together_generate_and_log')
    async def test_generate_success(self, mock_together_generate, monkeypatch):
        """Test generate method with successful response"""
        # Clear environment variables
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.utils.config.get_env', return_value=None):
            meta_llama_llm = MetaLlamaLLM(
                api_key="test-api-key",
                model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                temperature=0.7,
                max_tokens=512
            )

        expected_response = GenerateResponse(
            response="Test response from Meta Llama",
            prompt_tokens=15,
            completion_tokens=25,
            total_tokens=40,
            cost=0.002,
            model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
        )
        mock_together_generate.return_value = expected_response

        request = GenerateRequest(
            model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            prompt="What is machine learning?",
            parameters={"temperature": 0.5, "max_tokens": 256}
        )

        result = await meta_llama_llm.generate(request)

        # Verify the function was called (simplified assertion first)
        mock_together_generate.assert_called_once()
        
        # Get the actual call arguments
        args, kwargs = mock_together_generate.call_args
        
        # Verify key parameters individually
        assert kwargs['prompt'] == "What is machine learning?"
        assert kwargs['model'] == "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
        assert kwargs['api_key'] == "test-api-key"
        assert kwargs['temperature'] == 0.5
        assert kwargs['max_tokens'] == 256
        
        assert result == expected_response

    @pytest.mark.asyncio
    @patch('src.llms.Metallama_llm.together_generate_and_log')
    @patch('src.llms.Metallama_llm.handle_together_api_error')
    async def test_generate_exception_handling(self, mock_handle_error, mock_together_generate, monkeypatch):
        """Test generate method exception handling"""
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.utils.config.get_env', return_value=None):
            meta_llama_llm = MetaLlamaLLM(
                api_key="test-api-key",
                model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
            )

        mock_together_generate.side_effect = Exception("API connection failed")
        mock_handle_error.return_value = "Together API Error: API connection failed"

        request = GenerateRequest(
            model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            prompt="Test prompt",
            parameters={}
        )

        result = await meta_llama_llm.generate(request)

        assert result.response == ""
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
        assert result.total_tokens == 0
        assert result.cost == 0
        assert result.model == "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
        assert result.error == "Together API Error: API connection failed"

    @pytest.mark.asyncio
    @patch('src.llms.Metallama_llm.together_batch_generate_and_log')
    async def test_batch_generate_success(self, mock_batch_generate, monkeypatch):
        """Test batch_generate method"""
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.utils.config.get_env', return_value=None):
            meta_llama_llm = MetaLlamaLLM(
                api_key="test-api-key",
                model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                temperature=0.7,
                max_tokens=512
            )

        expected_responses = [
            GenerateResponse(response="Response 1", prompt_tokens=10, completion_tokens=15, total_tokens=25, cost=0.001, model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"),
            GenerateResponse(response="Response 2", prompt_tokens=12, completion_tokens=18, total_tokens=30, cost=0.002, model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo")
        ]
        mock_batch_generate.return_value = expected_responses

        requests = [
            GenerateRequest(model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", prompt="Prompt 1", parameters={"temperature": 0.5}),
            GenerateRequest(model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", prompt="Prompt 2", parameters={"temperature": 0.5})
        ]

        result = await meta_llama_llm.batch_generate(requests)

        # Verify the function was called
        mock_batch_generate.assert_called_once()
        
        # Get actual call arguments for debugging
        args, kwargs = mock_batch_generate.call_args
        
        # Verify key parameters
        assert kwargs['prompts'] == ["Prompt 1", "Prompt 2"]
        assert kwargs['model'] == "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
        assert kwargs['api_key'] == "test-api-key"
        assert kwargs['temperature'] == 0.5

        assert result == expected_responses
        assert len(result) == 2

    @pytest.mark.asyncio
    @patch('src.llms.Metallama_llm.together_batch_generate_and_log')
    async def test_batch_generate_empty_requests(self, mock_batch_generate, monkeypatch):
        """Test batch_generate with empty requests"""
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.utils.config.get_env', return_value=None):
            meta_llama_llm = MetaLlamaLLM(
                api_key="test-api-key",
                model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                temperature=0.7,
                max_tokens=512
            )

        mock_batch_generate.return_value = []

        result = await meta_llama_llm.batch_generate([])

        # Verify the function was called
        mock_batch_generate.assert_called_once()
        
        # Get actual call arguments
        args, kwargs = mock_batch_generate.call_args
        
        # Verify key parameters
        assert kwargs['prompts'] == []
        assert kwargs['model'] == "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
        assert kwargs['api_key'] == "test-api-key"

        assert result == []

    @pytest.mark.asyncio
    @patch('src.llms.Metallama_llm.together_batch_generate_and_log')
    @patch('src.llms.Metallama_llm.handle_together_api_error')
    async def test_batch_generate_exception_handling(self, mock_handle_error, mock_batch_generate, monkeypatch):
        """Test batch_generate method exception handling"""
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.utils.config.get_env', return_value=None):
            meta_llama_llm = MetaLlamaLLM(
                api_key="test-api-key",
                model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
            )

        mock_batch_generate.side_effect = Exception("Batch API failed")
        mock_handle_error.return_value = "Together API Error: Batch API failed"

        requests = [
            GenerateRequest(model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", prompt="Prompt 1", parameters={}),
            GenerateRequest(model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", prompt="Prompt 2", parameters={})
        ]

        result = await meta_llama_llm.batch_generate(requests)

        assert len(result) == 2
        for response in result:
            assert response.response == ""
            assert response.prompt_tokens == 0
            assert response.completion_tokens == 0
            assert response.total_tokens == 0
            assert response.cost == 0.0
            assert response.model == "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
            assert response.error == "Together API Error: Batch API failed"

    def test_init_with_custom_parameters(self, monkeypatch):
        """Test initialization with custom parameters"""
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.utils.config.get_env', return_value=None):
            llm = MetaLlamaLLM(
                api_key="custom-key",
                model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                temperature=0.9,
                max_tokens=1024,
                stop=["CUSTOM_STOP"],
                top_p=0.9,
                top_k=100,
                repetition_penalty=1.2,
                stream_tokens=True,
                safety_model="safety-model",
                n=3
            )
            
            assert llm.api_key == "custom-key"
            assert llm.model == "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
            assert llm.temperature == 0.9
            assert llm.max_tokens == 1024
            assert llm.stop == ["CUSTOM_STOP"]
            assert llm.top_p == 0.9
            assert llm.top_k == 100
            assert llm.repetition_penalty == 1.2
            assert llm.stream_tokens == True
            assert llm.safety_model == "safety-model"
            assert llm.n == 3

    def test_init_with_env_api_key(self, monkeypatch):
        """Test initialization with API key from environment"""
        # Set environment variable using monkeypatch
        monkeypatch.setenv("TOGETHER_API_KEY", "env-api-key")
        
        with patch('src.utils.config.get_env', return_value="env-api-key"):
            llm = MetaLlamaLLM(api_key="fallback-key", model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo")
            
            assert llm.api_key == "env-api-key"
