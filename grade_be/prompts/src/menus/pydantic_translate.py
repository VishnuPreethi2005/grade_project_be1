"""
This is used to format input and output
"""

import json
from typing import Optional
from utils.logging_utils import logger


from langchain.pydantic_v1 import BaseModel, validator


class TranslationInput(BaseModel):
    """
    Pydantic for translation parameters
    """

    text: Optional[str] = None
    destination: Optional[str] = None
    source: Optional[str] = None
    domain: Optional[str] = None  # Optional fields with default values
    subdomain: Optional[str] = None
    type_of_mail: Optional[str] = None
    tone: Optional[str] = None
    recipient: Optional[str] = None
    purpose: Optional[str] = None
    content: Optional[str] = None
    Entity: Optional[str] = None
    CustomEntity: Optional[str] = None
    # Questionwhiz
    questionType: Optional[str] = None
    numQuestionsValue: Optional[int] = None
    bloomValue: Optional[str] = None
    levelValue: Optional[str] = None
    numberOfOptionsValue: Optional[int] = None
    optionTypeValue: Optional[str] = None
    numberOfMissingWordsValue: Optional[int] = None
    representingWordsValue: Optional[str] = None
    numberOfItemsValue: Optional[int] = None
    learningObj: Optional[str] = None
    provideAnswerValue: Optional[str] = None
    explanationValue: Optional[str] = None
    formatValue: Optional[str] = None
    similar_question: Optional[str] = None
    topicValue: Optional[str] = None
    subtopicValue: Optional[str] = None
    exampleValue: Optional[str] = None
    conceptValue: Optional[str] = None
    constraintsValue: Optional[str] = None
    keywordsValue: Optional[str] = None

    @validator(
        "numberOfMissingWordsValue",
        "numberOfItemsValue",
        "numQuestionsValue",
        "numberOfOptionsValue",
        pre=True,
    )
    def _coerce_int(cls, value):
        if value in (None, "", "null"):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError("value is not a valid integer") from None

    class Config:
        """
        Allow extra fields and type coercion for frontend compatibility
        """
        extra = "allow"
        arbitrary_types_allowed = True
        use_enum_values = True
        allow_population_by_field_name = True
        smart_union = True
        validate_assignment = True


class PromptString(BaseModel):
    """
    Parameters to form the template in prompt
    """

    text_to_translate: str
    system_template: str
    template_full: str
    template_domain: Optional[str] = None
    template_subdomain: Optional[str] = None
    context_template: Optional[str] = None
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
