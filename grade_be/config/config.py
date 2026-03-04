# config/config.py

from pydantic_settings import BaseSettings

"""
Settings configuration for the Django application.

This module defines a settings class using Pydantic for configuring the Django application.

Classes:
    Settings:
        Configuration settings class for the Django application.
        Inherits from BaseSettings provided by Pydantic.

Attributes:
    openai_api_key (str):
        API key for accessing the OpenAI service.
    organization_id (str):
        ID of the organization associated with the Django application.

Configuration:
    Config:
        Inner class defining configuration options for the settings class.
        - env_file: Specifies the name of the .env file to load environment variables from.
        - env_prefix: Prefix for environment variables specific to the Django application.
"""


class Settings(BaseSettings):
    openai_api_key: str
    organization_id: str

    class Config:
        env_file = ".env"
        env_prefix = "MYDJANGOAPP_"
