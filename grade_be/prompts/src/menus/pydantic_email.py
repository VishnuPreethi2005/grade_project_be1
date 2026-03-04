import json
from typing import Optional
from utils.logging_utils import logger
from langchain.pydantic_v1 import BaseModel


class EmailWriterInput(BaseModel):
    """
    Pydantic for email writer parameters
    """

    recipient: str
    subject: str
    body: str
    sender: Optional[str] = None  # Optional fields with default values
    cc: Optional[str] = None
    bcc: Optional[str] = None

    class Config:
        """
        Don't allow unknown fields
        """

        extra = "forbid"


class EmailPromptString(BaseModel):
    """
    Parameters to form the template in prompt for email writer
    """

    recipient: str
    subject_template: str
    body_template: str
    sender_template: Optional[str] = None
    cc_template: Optional[str] = None
    bcc_template: Optional[str] = None
    context_template: Optional[str] = None
    output_format: Optional[str] = None

    class Config:
        """
        Don't allow unknown fields
        """

        extra = "forbid"


def clean_email_output(chat_response):
    """
    Convert the email writer string to a dictionary
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
