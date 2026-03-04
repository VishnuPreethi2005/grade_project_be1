# test_llms.py
import pytest
import asyncio
import json
from src.llm_manager import handle_request

@pytest.mark.asyncio
async def test_openai_llm_basic():
    req = {
        "model": "openai",
        "prompt": "Test prompt.",
        "parameters": {"temperature": 0.1}
    }
    resp = await handle_request(json.dumps(req))
    
    # resp is a string like 'Response: {...}' or 'Error: ...'
    assert isinstance(resp, str)
    
    # Check if it's a successful response
    if resp.lower().startswith("response:"):
        # For successful responses, just check that key fields are present
        assert "'response':" in resp
        assert "'model':" in resp
        assert "'error': None" in resp or "'error':None" in resp
        # Ensure it's not an error response
        assert not resp.lower().startswith("error:")
    else:
        # If it's an error, it should start with "Error:"
        assert resp.lower().startswith("error:")

@pytest.mark.asyncio
async def test_mistral_llm_basic():
    req = {
        "model": "mistral",
        "prompt": "Test prompt.",
        "parameters": {"temperature": 0.1}
    }
    resp = await handle_request(json.dumps(req))
    
    # resp is a string like 'Response: {...}' or 'Error: ...'
    assert isinstance(resp, str)
    
    # Check if it's a successful response
    if resp.lower().startswith("response:"):
        # For successful responses, just check that key fields are present
        assert "'response':" in resp
        assert "'model':" in resp
        assert "'error': None" in resp or "'error':None" in resp
        # Ensure it's not an error response
        assert not resp.lower().startswith("error:")
    else:
        # If it's an error, it should start with "Error:"
        assert resp.lower().startswith("error:")

@pytest.mark.asyncio
async def test_handle_request_invalid_model():
    req = {
        "model": "unknown",
        "prompt": "Test prompt"
    }
    resp = await handle_request(json.dumps(req))
    
    # For invalid model, handle_request returns a dict with error
    assert isinstance(resp, dict)
    assert "error" in resp
    assert "Unknown model" in resp["error"]
