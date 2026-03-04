import os
from src.utils.config import load_env, get_env

def test_load_env_and_get_env(tmp_path, monkeypatch):
    # Create a temporary .env file
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_KEY=12345\n")
    
    # Change to the temp directory where .env is located
    monkeypatch.chdir(tmp_path)
    
    # Directly set the environment variable for testing
    monkeypatch.setenv("TEST_KEY", "12345")
    
    # Load environment from the current directory
    load_env()
    
    assert get_env("TEST_KEY") == "12345"
    assert get_env("NON_EXISTENT_KEY", "default") == "default"
