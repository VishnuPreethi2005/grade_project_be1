"""
This is used to format input and output
"""

import json
from typing import Optional
from utils.logging_utils import logger


from langchain.pydantic_v1 import BaseModel


class TransliterationInput(BaseModel):
    """
    Pydantic for translation parameters
    """

    text: str
    destination: str
    source: str

    class Config:
        """
        Don't allow unknown fields
        """

        extra = "forbid"


class PromptString(BaseModel):
    """
    Parameters to form the template in prompt
    """

    text_to_translate: str
    system_template: str
    template_full: str
    # template_domain: Optional[str] = None
    # template_subdomain: Optional[str] = None
    # context_template: Optional[str] = None
    output_format: Optional[str] = None

    class Config:
        """
        Don't allow unknown fields
        """

        extra = "forbid"


def clean_output(chat_response):
    """
    Convert the string to a dictionary
    """
    if not isinstance(chat_response, str) or not chat_response.strip():
        logger.error("Error: chat_response is not a valid non-empty string")
        return (
            None  # or raise an exception or handle it according to your needs
        )

    try:
        data = json.loads(chat_response)

    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON: {e}")
        return (
            None  # or raise an exception or handle it according to your needs
        )

    # Iterate over items and format them
    formatted_strings = [f"{value}" for key, value in data.items()]

    # Join the formatted strings with a newline character
    result = " ".join(formatted_strings)
    logger.info("Result: %s", result)
    return result
