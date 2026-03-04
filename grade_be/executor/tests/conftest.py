import pytest

@pytest.fixture(autouse=True)
def set_dummy_api_keys(settings):
    settings.GEMINI_API_KEY = "dummy-gemini-key"
    settings.COHERE_API_KEY = "dummy-cohere-key"
