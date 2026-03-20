import json
from typing import Optional
from utils.logging_utils import logger

from langchain.pydantic_v1 import BaseModel


class EntityInput(BaseModel):
    """
    Pydantic model for entity task parameters.
    """

    text: str
    entity: Optional[str] = None
    custom_entity: Optional[str] = None

    class Config:
        """
        Don't allow unknown fields
        """

        extra = "forbid"


class EntityPromptString(BaseModel):
    """
    Parameters to form the template in prompt for entity tasks.
    """

    text_to_analyze: str
    system_template: str
    output_format: Optional[str] = None

    class Config:
        """
        Don't allow unknown fields
        """

        extra = "forbid"


def clean_entity_output(chat_response):
    """
    Convert the string to a dictionary and clean the entity output.
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
    formatted_strings = [f"{key}: {value}" for key, value in data.items()]

    # Join the formatted strings with a newline character
    result = "\n".join(formatted_strings)
    logger.info("Result: %s", result)
    return result
