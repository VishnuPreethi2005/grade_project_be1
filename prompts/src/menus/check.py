import logging
import asyncio
from typing import Any, Dict, Tuple, Union

from pydantic import BaseModel, Field
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.pydantic_v1 import BaseModel as LCBaseModel
from langchain_core.runnables import RunnablePassthrough

from prompts.src.models.openaimodels import ChatOpenAIModel
from prompts.src.models.TogetherModels import TogetherAIModel
from utils.exceptions import RetryableException, RetryLimitExceededException
from utils.logging_utils import logger
from langchain_core.pydantic_v1 import Field as LCField


# ===== PYDANTIC MODELS FOR STRUCTURED INPUT AND OUTPUT =====


class TranslationInput(BaseModel):
    """Input schema for translation and transliteration tasks."""

    text: str = Field(description="Text to translate or transliterate")
    source: str = Field(description="Source language")
    destination: str = Field(description="Destination language(s)")
    domain: str = Field(
        default="", description="Domain context for translation"
    )
    subdomain: str = Field(
        default="", description="Subdomain context for translation"
    )


class EntityInput(BaseModel):
    """Input schema for entity recognition tasks."""

    text: str = Field(description="Text to analyze for entities")
    Entity: str = Field(description="Entity types to identify")
    CustomEntity: str = Field(
        default="", description="Custom entity types to identify"
    )


class EmailWriterInput(BaseModel):
    """Input schema for email writing tasks."""

    type_of_mail: str = Field(description="Type of email to compose")
    tone: str = Field(description="Tone of the email")
    recipient: str = Field(description="Email recipient")
    purpose: str = Field(description="Purpose of the email")
    content: str = Field(description="Key points to include in the email")


class QuestionInput(BaseModel):
    """Input schema for question generation tasks."""

    questionType: str = Field(
        default="", description="Type of question to generate"
    )
    numQuestionsValue: str = Field(
        default="", description="Number of questions to generate"
    )
    bloomValue: str = Field(default="", description="Bloom's taxonomy level")
    levelValue: str = Field(default="", description="Difficulty level")
    numberOfOptionsValue: str = Field(
        default="", description="Number of options for MCQs"
    )
    optionTypeValue: str = Field(default="", description="Type of options")
    numberOfMissingWordsValue: str = Field(
        default="", description="Number of missing words"
    )
    representingWordsValue: str = Field(
        default="", description="Words to represent"
    )
    numberOfItemsValue: str = Field(default="", description="Number of items")
    learningObj: str = Field(default="", description="Learning objective")
    provideAnswerValue: str = Field(
        default="", description="Whether to provide answers"
    )
    explanationValue: str = Field(
        default="", description="Whether to provide explanations"
    )
    formatValue: str = Field(default="", description="Format of questions")
    text: str = Field(
        default="", description="Text to generate questions from"
    )
    similar_question: str = Field(
        default="", description="Similar question to base on"
    )
    topicValue: str = Field(default="", description="Topic for questions")
    subtopicValue: str = Field(
        default="", description="Subtopic for questions"
    )
    exampleValue: str = Field(default="", description="Example questions")
    conceptValue: str = Field(default="", description="Concept to focus on")
    constraintsValue: str = Field(
        default="", description="Constraints for questions"
    )
    keywordsValue: str = Field(default="", description="Keywords to include")


# ===== OUTPUT MODELS =====


class TranslationOutput(LCBaseModel):
    """Output schema for translation results."""

    destination_language: str = LCField(
        description="Name of the destination language"
    )
    translated_text: str = LCField(description="Translated text")


class MultiTranslationOutput(LCBaseModel):
    """Output schema for multi-language translation results."""

    translations: list[TranslationOutput] = LCField(
        description="List of translations"
    )


class EntityOutput(LCBaseModel):
    """Output schema for entity recognition results."""

    entities: dict[str, list[str]] = LCField(
        description="Recognized entities by type"
    )


class EmailOutput(LCBaseModel):
    """Output schema for email composition."""

    subject: str = LCField(description="Email subject line")
    body: str = LCField(
        description="Complete email body with greeting and closing"
    )


class QuestionOutput(LCBaseModel):
    """Output schema for generated questions."""

    questions: list[str] = LCField(description="List of generated questions")


# ===== PROMPT TEMPLATES =====


class BasePromptTemplate:
    """Base class for creating prompt templates."""

    def get_output_parser(self):
        """Return the appropriate output parser for this template."""
        raise NotImplementedError(
            "Subclasses must implement get_output_parser"
        )

    def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
        """Generate a prompt template based on input data."""
        raise NotImplementedError(
            "Subclasses must implement create_prompttemplate"
        )


class TranslatePromptTemplate(BasePromptTemplate):
    """Class for creating prompt templates for translation tasks."""

    def get_output_parser(self):
        return PydanticOutputParser(pydantic_object=MultiTranslationOutput)


class TranslatePromptTemplate(BasePromptTemplate):
    """Class for creating prompt templates for translation tasks."""

    def get_output_parser(self):
        return PydanticOutputParser(pydantic_object=MultiTranslationOutput)

    def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
        """Generate a prompt template for translation."""
        try:
            # System prompt
            system_template = (
                "You are a professional translator. Translate the provided text from the source language "
                "to the specified destination language(s), maintaining the original meaning and context."
            )

            # Human message template
            text_to_translate = (
                "Source Language: {source}\n"
                "Destination Language(s): {destination}\n"
                "Text to Translate: {text}\n"
            )

            # Context template based on provided information
            context_template = ""
            if input_data.get("domain"):
                context_template += f"Domain: {input_data['domain']}\n"
            if input_data.get("subdomain"):
                context_template += f"Subdomain: {input_data['subdomain']}\n"

            # Correct output format guide with ESCAPED curly braces
            output_format_guide = (
                "\nPlease provide the translations in the following format:\n"
                "```"
                "{{\n"
                '  "translations": [\n'
                "    {{\n"
                '      "destination_language": "[language name]",\n'
                '      "translated_text": "[translated content]"\n'
                "    }}\n"
                "  ]\n"
                "}}\n"
                "```"
            )

            # Create chat template with messages
            chat_template = ChatPromptTemplate.from_messages(
                [
                    SystemMessagePromptTemplate.from_template(system_template),
                    HumanMessagePromptTemplate.from_template(
                        text_to_translate
                        + context_template
                        + output_format_guide
                    ),
                ],
            )

            return chat_template
        except Exception as e:
            logger.error(
                f"Error occurred during translation prompt creation: {e}"
            )
            raise


class TransliteratePromptTemplate(BasePromptTemplate):
    """Class for creating prompt templates for transliteration tasks."""

    def get_output_parser(self):
        return PydanticOutputParser(pydantic_object=MultiTranslationOutput)

    def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
        """Generate a prompt template for transliteration."""
        try:
            # System prompt
            system_template = (
                "You are a professional transliterator. Transliterate the provided text from the source language "
                "to the specified destination language(s), preserving pronunciation but using the destination "
                "language's writing system. Do not translate the meaning."
            )

            # Human message template
            text_to_transliterate = (
                "Source Language: {source}\n"
                "Destination Language(s): {destination}\n"
                "Text to Transliterate: {text}\n"
            )

            # Append formatting guidance manually
            output_format_guide = (
                "\nPlease provide the transliterations in the following format:\n"
                "```"
                "{\n"
                '  "translations": [\n'
                "    {\n"
                '      "destination_language": "[language name]",\n'
                '      "translated_text": "[transliterated content]"\n'
                "    },\n"
                "    ...\n"
                "  ]\n"
                "}\n"
                "```\n"
            )

            # Create chat template with messages
            chat_template = ChatPromptTemplate.from_messages(
                [
                    SystemMessagePromptTemplate.from_template(system_template),
                    HumanMessagePromptTemplate.from_template(
                        text_to_transliterate + output_format_guide
                    ),
                ],
            )

            return chat_template
        except Exception as e:
            logger.error(
                f"Error occurred during transliteration prompt creation: {e}"
            )
            raise


class EntityPromptTemplate(BasePromptTemplate):
    """Class for creating prompt templates for entity recognition tasks."""

    def get_output_parser(self):
        return PydanticOutputParser(pydantic_object=EntityOutput)

    def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
        """Generate a prompt template for entity recognition."""
        try:
            # System prompt
            system_template = "You are an expert in named entity recognition. Identify the specified entity types in the provided text."

            # Human message template
            text_to_analyze = (
                "Text: {text}\n" "Entity Types to Identify: {Entity}\n"
            )

            if input_data.get("CustomEntity"):
                text_to_analyze += "Custom Entity Types: {CustomEntity}\n"

            # Append formatting guidance manually
            output_format_guide = (
                "\nPlease provide the identified entities in the following format:\n"
                "```"
                "{\n"
                '  "entities": {\n'
                '    "entity_type1": ["entity1", "entity2", ...],\n'
                '    "entity_type2": ["entity1", "entity2", ...],\n'
                "    ...\n"
                "  }\n"
                "}\n"
                "```\n"
            )

            # Create chat template with messages
            chat_template = ChatPromptTemplate.from_messages(
                [
                    SystemMessagePromptTemplate.from_template(system_template),
                    HumanMessagePromptTemplate.from_template(
                        text_to_analyze + output_format_guide
                    ),
                ],
            )

            return chat_template
        except Exception as e:
            logger.error(f"Error occurred during entity prompt creation: {e}")
            raise


class EmailWriterPromptTemplate(BasePromptTemplate):
    def get_output_parser(self):
        return PydanticOutputParser(pydantic_object=EmailOutput)

    def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
        system_template = (
            "You are an expert email composer. Craft professional emails with:"
            "\n- Clear subject lines"
            "\n- Proper greeting/closing"
            "\n- Logical structure"
        )

        email_details = (
            "COMPOSITION BRIEF:\n"
            "Type: {type_of_mail}\n"
            "Tone: {tone}\n"
            "Recipient: {recipient}\n"
            "Purpose: {purpose}\n"
            "Key Points: {content}\n"
        )

        output_format_guide = (
            "\nFORMAT REQUIREMENTS:\n"
            """```
            "{{\n"  # Escaped opening brace
            "  \"subject\": \"[Subject Line Here]\",\n"
            "  \"body\": \"[Complete Email Body]\"\n"
            "}}\n"  # Escaped closing brace
            "```\n"
            "1. Subject line <= 60 characters\n"
            "2. Body contains 3-5 paragraphs\n"
            "3. Use professional sign-off"""
        )

        return ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(system_template),
                HumanMessagePromptTemplate.from_template(
                    email_details + output_format_guide
                ),
            ]
        )


class QuestionGeneratorPromptTemplate(BasePromptTemplate):
    """Base class for question generation prompt templates."""

    def get_output_parser(self):
        return PydanticOutputParser(pydantic_object=QuestionOutput)

    def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
        """Generate a prompt template for question generation."""
        try:
            # System prompt
            system_template = (
                "You are an expert at generating high-quality questions based on provided text. "
                "Create clear, concise, and relevant questions that probe understanding of the content."
            )

            # Human message template
            text_for_questions = (
                "Text: {text}\n"
                "Question Type: {questionType}\n"
                "Number of Questions: {numQuestionsValue}\n"
                "Bloom's Taxonomy Level: {bloomValue}\n"
                "Difficulty Level: {levelValue}\n"
                "Number of Options: {numberOfOptionsValue}\n"
                "Option Type: {optionTypeValue}\n"
                "Number of Missing Words: {numberOfMissingWordsValue}\n"
                "Representing Words: {representingWordsValue}\n"
                "Number of Items: {numberOfItemsValue}\n"
                "Learning Objective: {learningObj}\n"
                "Provide Answer: {provideAnswerValue}\n"
                "Provide Explanation: {explanationValue}\n"
                "Format: {formatValue}\n"
            )

            # Append formatting guidance manually
            output_format_guide = (
                "\nPlease provide the generated questions in the following format:\n"
                "```"
                "{\n"
                '  "questions": [\n'
                '    "[question 1]",\n'
                '    "[question 2]",\n'
                "    ...\n"
                "  ]\n"
                "}\n"
                "```\n"
            )

            # Create chat template with messages
            chat_template = ChatPromptTemplate.from_messages(
                [
                    SystemMessagePromptTemplate.from_template(system_template),
                    HumanMessagePromptTemplate.from_template(
                        text_for_questions + output_format_guide
                    ),
                ],
            )

            return chat_template
        except Exception as e:
            logger.error(
                f"Error occurred during question generator prompt creation: {e}"
            )
            raise


class SimilarQuestionPromptTemplate(QuestionGeneratorPromptTemplate):
    """Class for creating prompt templates for similar question generation."""

    def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
        """Generate a prompt template for similar question generation."""
        try:
            # System prompt
            system_template = (
                "You are an expert at generating similar questions based on a provided question or text. "
                "Create variations that probe the same concept but from different angles or with different wording."
            )

            # Human message template
            text_for_questions = (
                "Original Question/Text: {text}\n"
                "Generate similar questions that address the same core concepts but with different phrasing or focus.\n"
            )

            # Append formatting guidance manually
            output_format_guide = """
                \nPlease provide the similar questions in the following format:\n

                {
                  "questions": [
                    "[similar question 1]",
                    "[similar question 2]",
                    ...
                  ]
                }
                ```
                """

            # Create chat template with messages
            chat_template = ChatPromptTemplate.from_messages(
                [
                    SystemMessagePromptTemplate.from_template(system_template),
                    HumanMessagePromptTemplate.from_template(
                        text_for_questions + output_format_guide
                    ),
                ],
            )

            return chat_template

        except Exception as e:
            logger.error(
                f"Error occurred during similar question prompt creation: {e}"
            )
            raise


class TopicBasedQuestionPromptTemplate(QuestionGeneratorPromptTemplate):
    """Class for creating prompt templates for topic-based question generation."""

    def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
        """Generate a prompt template for topic-based question generation."""
        try:
            # System prompt
            system_template = (
                "You are an expert at generating comprehensive questions on specific topics. "
                "Create questions that explore different aspects and depths of the provided topic."
            )

            # Human message template
            text_for_questions = (
                "Topic: {text}\n"
                "Generate a diverse set of questions covering various aspects of this topic, "
                "ranging from basic understanding to advanced analysis.\n"
            )

            # Append formatting guidance manually
            output_format_guide = (
                "\nPlease provide the topic-based questions in the following format:\n"
                "```"
                "{\n"
                '  "questions": [\n'
                '    "[topic question 1]",\n'
                '    "[topic question 2]",\n'
                "    ...\n"
                "  ]\n"
                "}\n"
                "```\n"
            )

            # Create chat template with messages
            chat_template = ChatPromptTemplate.from_messages(
                [
                    SystemMessagePromptTemplate.from_template(system_template),
                    HumanMessagePromptTemplate.from_template(
                        text_for_questions + output_format_guide
                    ),
                ],
            )

            return chat_template
        except Exception as e:
            logger.error(
                f"Error occurred during topic-based question prompt creation: {e}"
            )
            raise


# ===== PROMPT RESPONSE HANDLING =====


class PromptResponse:
    """Class responsible for handling prompt responses from language models."""

    @staticmethod
    async def get_response(
        chain, input_data: Union[BaseModel, Dict]
    ) -> Tuple[Any, Any]:
        """
        Get a response from the model using the provided chain and input data.
        """
        try:
            from langchain_community.callbacks import get_openai_callback

            with get_openai_callback() as cb:
                # Handle both BaseModel and dict inputs
                data = (
                    input_data.dict()
                    if hasattr(input_data, "dict")
                    else input_data
                )

                # Remove any problematic formatting in keys
                if isinstance(data, dict):
                    # Clean up any keys with newlines or special formatting
                    cleaned_data = {}
                    for k, v in data.items():
                        if isinstance(k, str) and ("\n" in k or "  " in k):
                            # Create a clean key without newlines and extra
                            # spaces
                            clean_k = (
                                k.replace("\n", "").replace("  ", " ").strip()
                            )
                            cleaned_data[clean_k] = v
                        else:
                            cleaned_data[k] = v
                    data = cleaned_data

                response = await chain.ainvoke(data)
                return response, cb
        except Exception as e:
            logger.error(f"Error in get_response: {e}")
            raise


# ===== PIPELINE CLASS =====


class Pipeline:
    """
    A pipeline class that handles generating prompts, loading models, and
    processing prompts using the loaded models with structured output.
    """

    def __init__(self):
        self.prompt_response = PromptResponse()

        # Register handlers for different menu types
        self.menu_handlers = {
            "translate": {
                "template_class": TranslatePromptTemplate,
                "input_class": TranslationInput,
                "clean_output": self._clean_translation_output,
            },
            "transliterate": {
                "template_class": TransliteratePromptTemplate,
                "input_class": TranslationInput,
                "clean_output": self._clean_translation_output,
            },
            "entity": {
                "template_class": EntityPromptTemplate,
                "input_class": EntityInput,
                "clean_output": lambda x: x,  # No cleaning needed
            },
            "write_email": {
                "template_class": EmailWriterPromptTemplate,
                "input_class": EmailWriterInput,
                "clean_output": lambda x: x,  # No cleaning needed
            },
            "enter_text": {
                "template_class": QuestionGeneratorPromptTemplate,
                "input_class": QuestionInput,
                "clean_output": lambda x: x,  # No cleaning needed
            },
            "similarQuestion": {
                "template_class": SimilarQuestionPromptTemplate,
                "input_class": QuestionInput,
                "clean_output": lambda x: x,  # No cleaning needed
            },
            "topic": {
                "template_class": TopicBasedQuestionPromptTemplate,
                "input_class": QuestionInput,
                "clean_output": lambda x: x,  # No cleaning needed
            },
        }

    def _clean_translation_output(self, output):
        """Clean and format translation output."""
        if isinstance(output, dict) and "translations" in output:
            return output
        return output

    async def async_pipeline_process(
        self, menu: str, model_dict: dict, input_data: dict
    ) -> tuple:
        """
        Process the pipeline from prompt generation to prompt processing with structured output.

        Args:
            menu: The menu type (translate, entity, etc.)
            model_dict: Configuration for the model
            input_data: Input data for the prompt

        Returns:
            tuple: Response content and cost
        """
        try:
            # Check if menu type is supported
            if menu not in self.menu_handlers:
                raise ValueError(f"Unsupported menu type: {menu}")

            # Get the handler for this menu type
            handler = self.menu_handlers[menu]

            # Create template and validate input
            menu_object = handler["template_class"]()
            logging.info(f"{menu.capitalize()} Object Created")

            # Validate input data with Pydantic
            input_class = handler["input_class"]
            validated_data = input_class(**input_data)
            logging.info("Validated Data with Pydantic")

            # Prepare input for prompt template
            prompt_input = validated_data.dict()

            # Add a translations placeholder for translation-related tasks
            if menu in ["translate", "transliterate"]:
                # Ensure "translations" exists
                prompt_input["translations"] = []

            # Create prompt template
            prompt_template = menu_object.create_prompttemplate(prompt_input)
            logging.info("Prompt Created")

            # Get output parser
            output_parser = menu_object.get_output_parser()
            openAIModels = [
                "gpt-3.5-turbo",
                "gpt-4-1106-preview",
                "gpt-4",
                "gpt-4-turbo",
                "gpt-4o",
                "gpt-4.5-preview",
            ]

            # Create chain with output parsing
            if model_dict["model"] in openAIModels:
                model_object = ChatOpenAIModel()
                logging.info("ChatOpenAI Object Created")
                model = model_object.create_model(model_dict)
                logging.info("Model Created")

                try:
                    # Attempt with output parser
                    chain = (
                        RunnablePassthrough()
                        | prompt_template
                        | model
                        | output_parser
                    )
                    logging.info("Chain Created with Output Parser")

                    response_content, cost = (
                        await self.prompt_response.get_response(
                            chain, prompt_input
                        )
                    )
                    logging.info("Response received with structured output")

                    clean_output_fn = handler["clean_output"]
                    result = clean_output_fn(response_content)

                    return result, cost

                except Exception as parsing_error:
                    # If parsing fails, create a chain without the output
                    # parser
                    logging.warning(
                        f"Output parsing failed: {str(parsing_error)}. Returning raw output."
                    )
                    chain_without_parser = (
                        RunnablePassthrough() | prompt_template | model
                    )

                    # Get raw output from model
                    raw_response, cost = (
                        await self.prompt_response.get_response(
                            chain_without_parser, prompt_input
                        )
                    )

                    # For raw responses, we need to extract the content
                    if hasattr(raw_response, "content"):
                        raw_content = raw_response.content
                    else:
                        raw_content = str(raw_response)

                    # Return the raw output with a flag indicating parsing
                    # failed
                    return {
                        "raw_output": raw_content,
                        "parsing_failed": True,
                    }, cost

            else:
                model_object = TogetherAIModel()
                logging.info("Together Object Created")
                model = model_object.create_model(model_dict)
                logging.info("Model Created")

                try:
                    # Attempt with output parser
                    chain = (
                        RunnablePassthrough()
                        | prompt_template
                        | model
                        | output_parser
                    )
                    logging.info("Chain Created with Output Parser")

                    response_content, _ = (
                        await self.prompt_response.get_response(
                            chain, prompt_input
                        )
                    )
                    logging.info("Response received with structured output")
                    return response_content, 0

                except Exception as parsing_error:
                    # If parsing fails, create a chain without the output
                    # parser
                    logging.warning(
                        f"Output parsing failed: {str(parsing_error)}. Returning raw output."
                    )
                    chain_without_parser = (
                        RunnablePassthrough() | prompt_template | model
                    )

                    # Get raw output from model
                    raw_response, _ = await self.prompt_response.get_response(
                        chain_without_parser, prompt_input
                    )

                    # For raw responses, we need to extract the content
                    if hasattr(raw_response, "content"):
                        raw_content = raw_response.content
                    else:
                        raw_content = str(raw_response)

                    # Return the raw output with a flag indicating parsing
                    # failed
                    return {
                        "raw_output": raw_content,
                        "parsing_failed": True,
                    }, 0

        except Exception as e:
            logger.exception(f"Critical pipeline failure: {str(e)}")
            raise RetryableException("Temporary service interruption") from e

    # async def async_pipeline_process(self, menu: str, model_dict: dict, input_data: dict) -> tuple:
    #     """
    # Process the pipeline from prompt generation to prompt processing with
    # structured output.

    #     Args:
    #         menu: The menu type (translate, entity, etc.)
    #         model_dict: Configuration for the model
    #         input_data: Input data for the prompt

    #     Returns:
    #         tuple: Response content and cost
    #     """
    #     try:
    #         # Check if menu type is supported
    #         if menu not in self.menu_handlers:
    #             raise ValueError(f"Unsupported menu type: {menu}")

    #         # Get the handler for this menu type
    #         handler = self.menu_handlers[menu]

    #         # Create template and validate input
    #         menu_object = handler["template_class"]()
    #         logging.info(f"{menu.capitalize()} Object Created")

    #         # Validate input data with Pydantic
    #         input_class = handler["input_class"]
    #         validated_data = input_class(**input_data)
    #         logging.info("Validated Data with Pydantic")

    #         # Prepare input for prompt template
    #         prompt_input = validated_data.dict()

    #         # Add a translations placeholder for translation-related tasks
    #         if menu in ["translate", "transliterate"]:
    # prompt_input["translations"] = []  # Ensure "translations" exists

    #         # Create prompt template
    #         prompt_template = menu_object.create_prompttemplate(prompt_input)
    #         logging.info("Prompt Created")

    #         # Get output parser
    #         output_parser = menu_object.get_output_parser()
    #         openAIModels = [
    #             "gpt-3.5-turbo", "gpt-4-1106-preview", "gpt-4",
    #             "gpt-4-turbo", "gpt-4o", "gpt-4.5-preview"
    #         ]
    #         # Create chain with output parsing
    #         if model_dict["model"] in openAIModels:
    #             model_object = ChatOpenAIModel()
    #             logging.info("ChatOpenAI Object Created")
    #             model = model_object.create_model(model_dict)
    #             logging.info("Model Created")

    #             chain = RunnablePassthrough() | prompt_template | model | output_parser
    #             logging.info("Chain Created with Output Parser")

    #             response_content, cost = await self.prompt_response.get_response(chain, prompt_input)
    #             logging.info("Response received with structured output")

    #             clean_output_fn = handler["clean_output"]
    #             result = clean_output_fn(response_content)

    #             return result, cost

    #         else:
    #             model_object = TogetherAIModel()
    #             logging.info("Together Object Created")
    #             print(model_dict)
    #             model = model_object.create_model(model_dict)
    #             logging.info("Model Created")

    #             chain = RunnablePassthrough() | prompt_template | model | output_parser
    #             logging.info("Chain Created with Output Parser")

    #             response_content, _ = await self.prompt_response.get_response(chain, prompt_input)
    #             logging.info("Response received with structured output")
    #             print(response_content)
    #             return response_content, 0

    #             # return result, cost

    #     except Exception as e:
    #         logger.exception(f"Critical pipeline failure: {str(e)}")
    #         raise RetryableException("Temporary service interruption") from e


async def start_point(
    menu: str, model_dict: Dict[str, Any], input_dict: Dict[str, Any]
) -> Union[Tuple[Any, float], Exception]:
    """
    Entry point for the pipeline processing with retry logic.

    Args:
        menu: The menu type
        model_dict: Configuration for the model
        input_dict: Input data

    Returns:
        tuple: Result and cost, or raises an exception after max retries
    """
    max_retries = 3
    retry_delay_seconds = 1

    for retry_count in range(max_retries):
        try:
            pipeline = Pipeline()
            response = await pipeline.async_pipeline_process(
                menu, model_dict, input_dict
            )

            # Determine which models are from OpenAI
            openAIModels = [
                "gpt-3.5-turbo",
                "gpt-4-1106-preview",
                "gpt-4",
                "gpt-4-turbo",
                "gpt-4o",
                "gpt-4.5-preview",
            ]

            if model_dict["model"] in openAIModels:
                result = response[0]
                cost = response[1]
            else:
                result = response[0]
                cost = 0

            # Log result
            if isinstance(result, dict) and result.get(
                "parsing_failed", False
            ):
                logger.info(
                    f"Menu: {menu}, Cost: {cost}, Returned raw output due to parsing failure"
                )
            else:
                logger.info(f"Menu: {menu}, Cost: {cost}, Result: {result}")
            print(result)
            return result, cost

        except RetryableException as e:
            logger.warning(f"Retrying (attempt {retry_count + 1}) due to: {e}")
            await asyncio.sleep(retry_delay_seconds)
        except Exception as e:
            logger.exception(f"Exception in start_point: {e}")
            raise

    # If all retries fail
    logger.error("Maximum retries reached. Failed to process.")
    raise RetryLimitExceededException("Maximum retries reached.")
