from dotenv import load_dotenv
from pathlib import Path
import os


def load_env():
    env_path = Path(__file__).parent.parent / '.env'  # This points to src/.env
    load_dotenv(dotenv_path=env_path)


load_env()

def get_env(key: str, default=None):
    return os.getenv(key, default)
