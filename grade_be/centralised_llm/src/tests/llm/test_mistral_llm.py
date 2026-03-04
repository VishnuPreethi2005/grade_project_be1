# test_mistral_llm.py
import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from src.llms.mistral_llm import MistralLLM
from src.llm_base import GenerateRequest, GenerateResponse


class TestMistralLLM:
    """Test suite for MistralLLM class."""

    def test_init(self, monkeypatch):
        """Test MistralLLM initialization with monkeypatch for env vars."""
        # Use monkeypatch to clear environment variables
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.utils.config.get_env', return_value=None):
            llm = MistralLLM(
                api_key="test-api-key",
                model="mistralai/Mistral-7B-Instruct-v0.1",
                temperature=0.7,
                max_tokens=100
            )
            
            assert llm.api_key == "test-api-key"
            assert llm.model == "mistralai/Mistral-7B-Instruct-v0.1"
            assert llm.temperature == 0.7
            assert llm.max_tokens == 100
            assert llm.stop == ["</s>", "[/INST]"]
            assert llm.top_p == 0.7
            assert llm.top_k == 50
            assert llm.repetition_penalty == 1.0
            assert llm.stream_tokens == False
            assert llm.safety_model is None
            assert llm.n == 1
            assert llm.provider_key == "Mistral AI"
            assert isinstance(llm.pricing_json_path, Path)
            assert llm.pricing_json_path.name == "llm_pricing.json"

    @pytest.mark.asyncio
    @patch('src.llms.mistral_llm.together_generate_and_log')
    async def test_generate_success(self, mock_together_generate, monkeypatch):
        """Test generate method with successful response"""
        # Clear environment variables
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.utils.config.get_env', return_value=None):
            mistral_llm = MistralLLM(
                api_key="test-api-key",
                model="mistralai/Mistral-7B-Instruct-v0.1",
                temperature=0.7,
                max_tokens=100
            )

        expected_response = GenerateResponse(
            response="Test response from Mistral",
            prompt_tokens=15,
            completion_tokens=25,
            total_tokens=40,
            cost=0.002,
            model="mistralai/Mistral-7B-Instruct-v0.1"
        )
        mock_together_generate.return_value = expected_response

        request = GenerateRequest(
            model="mistralai/Mistral-7B-Instruct-v0.1",
            prompt="What is machine learning?",
            parameters={"temperature": 0.5, "max_tokens": 50}
        )

        result = await mistral_llm.generate(request)

        # Check what was actually called to debug
        actual_call = mock_together_generate.call_args
        print(f"Actual call: {actual_call}")

        # Verify the function was called (simplified assertion first)
        mock_together_generate.assert_called_once()
        
        # Get the actual call arguments
        args, kwargs = mock_together_generate.call_args
        
        # Verify key parameters individually
        assert kwargs['prompt'] == "What is machine learning?"
        assert kwargs['model'] == "mistralai/Mistral-7B-Instruct-v0.1"
        assert kwargs['api_key'] == "test-api-key"
        assert kwargs['temperature'] == 0.5
        assert kwargs['max_tokens'] == 50
        
        assert result == expected_response

    @pytest.mark.asyncio
    @patch('src.llms.mistral_llm.together_generate_and_log')
    @patch('src.llms.mistral_llm.handle_together_api_error')
    async def test_generate_exception_handling(self, mock_handle_error, mock_together_generate, monkeypatch):
        """Test generate method exception handling"""
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.utils.config.get_env', return_value=None):
            mistral_llm = MistralLLM(
                api_key="test-api-key",
                model="mistralai/Mistral-7B-Instruct-v0.1"
            )

        mock_together_generate.side_effect = Exception("API connection failed")
        mock_handle_error.return_value = "Together API Error: API connection failed"

        request = GenerateRequest(
            model="mistralai/Mistral-7B-Instruct-v0.1",
            prompt="Test prompt",
            parameters={}
        )

        result = await mistral_llm.generate(request)

        assert result.response == ""
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
        assert result.total_tokens == 0
        assert result.cost == 0
        assert result.model == "mistralai/Mistral-7B-Instruct-v0.1"
        assert result.error == "Together API Error: API connection failed"

    @pytest.mark.asyncio
    @patch('src.llms.mistral_llm.together_batch_generate_and_log')
    async def test_batch_generate_success(self, mock_batch_generate, monkeypatch):
        """Test batch_generate method"""
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.utils.config.get_env', return_value=None):
            mistral_llm = MistralLLM(
                api_key="test-api-key",
                model="mistralai/Mistral-7B-Instruct-v0.1",
                temperature=0.7,
                max_tokens=100
            )

        expected_responses = [
            GenerateResponse(response="Response 1", prompt_tokens=10, completion_tokens=15, total_tokens=25, cost=0.001, model="mistralai/Mistral-7B-Instruct-v0.1"),
            GenerateResponse(response="Response 2", prompt_tokens=12, completion_tokens=18, total_tokens=30, cost=0.002, model="mistralai/Mistral-7B-Instruct-v0.1")
        ]
        mock_batch_generate.return_value = expected_responses

        requests = [
            GenerateRequest(model="mistralai/Mistral-7B-Instruct-v0.1", prompt="Prompt 1", parameters={"temperature": 0.5}),
            GenerateRequest(model="mistralai/Mistral-7B-Instruct-v0.1", prompt="Prompt 2", parameters={"temperature": 0.5})
        ]

        result = await mistral_llm.batch_generate(requests)

        # Verify the function was called
        mock_batch_generate.assert_called_once()
        
        # Get actual call arguments for debugging
        args, kwargs = mock_batch_generate.call_args
        
        # Verify key parameters
        assert kwargs['prompts'] == ["Prompt 1", "Prompt 2"]
        assert kwargs['model'] == "mistralai/Mistral-7B-Instruct-v0.1"
        assert kwargs['api_key'] == "test-api-key"
        assert kwargs['temperature'] == 0.5

        assert result == expected_responses
        assert len(result) == 2

    @pytest.mark.asyncio
    @patch('src.llms.mistral_llm.together_batch_generate_and_log')
    async def test_batch_generate_empty_requests(self, mock_batch_generate, monkeypatch):
        """Test batch_generate with empty requests"""
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.utils.config.get_env', return_value=None):
            mistral_llm = MistralLLM(
                api_key="test-api-key",
                model="mistralai/Mistral-7B-Instruct-v0.1",
                temperature=0.7,
                max_tokens=100
            )

        mock_batch_generate.return_value = []

        result = await mistral_llm.batch_generate([])

        # Verify the function was called
        mock_batch_generate.assert_called_once()
        
        # Get actual call arguments
        args, kwargs = mock_batch_generate.call_args
        
        # Verify key parameters
        assert kwargs['prompts'] == []
        assert kwargs['model'] == "mistralai/Mistral-7B-Instruct-v0.1"
        assert kwargs['api_key'] == "test-api-key"

        assert result == []

    @pytest.mark.asyncio
    @patch('src.llms.mistral_llm.together_batch_generate_and_log')
    @patch('src.llms.mistral_llm.handle_together_api_error')
    async def test_batch_generate_exception_handling(self, mock_handle_error, mock_batch_generate, monkeypatch):
        """Test batch_generate method exception handling"""
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.utils.config.get_env', return_value=None):
            mistral_llm = MistralLLM(
                api_key="test-api-key",
                model="mistralai/Mistral-7B-Instruct-v0.1"
            )

        mock_batch_generate.side_effect = Exception("Batch API failed")
        mock_handle_error.return_value = "Together API Error: Batch API failed"

        requests = [
            GenerateRequest(model="mistralai/Mistral-7B-Instruct-v0.1", prompt="Prompt 1", parameters={}),
            GenerateRequest(model="mistralai/Mistral-7B-Instruct-v0.1", prompt="Prompt 2", parameters={})
        ]

        result = await mistral_llm.batch_generate(requests)

        assert len(result) == 2
        for response in result:
            assert response.response == ""
            assert response.prompt_tokens == 0
            assert response.completion_tokens == 0
            assert response.total_tokens == 0
            assert response.cost == 0.0
            assert response.model == "mistralai/Mistral-7B-Instruct-v0.1"
            assert response.error == "Together API Error: Batch API failed"

    def test_init_with_custom_parameters(self, monkeypatch):
        """Test initialization with custom parameters"""
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
        
        with patch('src.utils.config.get_env', return_value=None):
            llm = MistralLLM(
                api_key="custom-key",
                model="mistralai/Mixtral-8x7B-Instruct-v0.1",
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
            assert llm.model == "mistralai/Mixtral-8x7B-Instruct-v0.1"
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
            llm = MistralLLM(api_key="fallback-key", model="mistralai/Mistral-7B-Instruct-v0.1")
            
            assert llm.api_key == "env-api-key"
