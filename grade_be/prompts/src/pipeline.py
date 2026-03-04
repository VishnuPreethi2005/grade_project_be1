# import logging
# import asyncio
# from typing import Any, Dict

# from pydantic import ValidationError, BaseModel

# from prompts.src.menus.pydantic_translate import TranslationInput, clean_output
# from prompts.src.menus.pydantic_entity import EntityInput, clean_entity_output
# from prompts.src.menus.translate import TranslateCreatePromptTemplate
# from prompts.src.menus.EmailWriter import EmailWriterCreatePromptTemplate
# from prompts.src.menus.Transliteration import TransliterateCreatePromptTemplate
# from prompts.src.menus.EnterText import QuestionCreatePromptTemplate
# from prompts.src.menus.SimilarQuestion import SimilarQuestionCreatePromptTemplate
# from prompts.src.menus.topic import TopicBasedQuestionCreatePromptTemplate
# from prompts.src.menus.Entity import EntityPromptTemplate
# from prompts.src.models.openaimodels import ChatOpenAIModel
# from prompts.src.models.TogetherModels import TogetherAIModel
# from prompts.src.process_prompt import PromptResponse
# from utils.exceptions import RetryableException, RetryLimitExceededException
# from utils.logging_utils import logger
# from validate.jevaluate import json_validate

# class TransliterationInput(BaseModel):
#     text: str
#     source: str
#     destination: str

# class Pipeline:
#     """
#     A pipeline class that handles generating prompts, loading models, and
#     processing prompts using the loaded models.
#     """

#     def __init__(self):
#         """
#         Initializes the pipeline with necessary components for prompt generation,
#         model loading, and prompt processing.
#         """
#         self.prompt_response = PromptResponse()

#     async def async_pipeline_process(self, menu: str, model_dict: dict, input_data: dict) -> tuple:
#         """
#         Processes the entire pipeline from prompt generation to prompt processing and
#         returns the response content and cost.

#         Args:
#             menu (str): The menu configuration string ("translate" or "transliterate").
#             model_dict (dict): The model configuration dictionary containing information
#             about the model to be loaded.
#             input_data (dict): The input dictionary data containing parameters
#             for prompt generation.

#         Returns:
#             tuple[str, float]: A tuple containing the response content and cost.
#         """
#         # Configure logging
#         logging.basicConfig(
#             filename="prompts/app.log",
#             level=logging.INFO,
#             filemode="w",
#             format="%(name)s - %(levelname)s - %(message)s",
#         )

#         try:
#             # Validate input data and create the prompt
#             if menu == "translate":
#                 menu_object = TranslateCreatePromptTemplate()
#                 logging.info("Translate Object Created")
#                 try:
#                     validated_data = TranslationInput(**input_data)
#                     logging.info("Validated Data with Pydantic")
#                 except ValidationError as e:
#                     logger.error("Validation error: %s", e)
#                     raise
#             elif menu == "transliterate":
#                 menu_object = TransliterateCreatePromptTemplate()
#                 logging.info("Transliterate Object Created")
#                 try:
#                     validated_data = TranslationInput(**input_data)
#                     logging.info("Validated Data with Pydantic")
#                 except ValidationError as e:
#                     logger.error("Validation error: %s", e)
#                     raise
#             elif menu == "entity":
#                 menu_object = EntityPromptTemplate()
#                 logging.info("Entity Recognizer Object Created")
#                 try:
#                     validated_data = TranslationInput(**input_data)
#                     logging.info("Validated Data with Pydantic")
#                 except ValidationError as e:
#                     logger.error("Validation error: %s", e)
#                     raise
#             elif menu == "write_email":

#                 menu_object = EmailWriterCreatePromptTemplate()

#                 logging.info("EmailWriter Object Created")
#                 try:
#                     validated_data = TranslationInput(**input_data)

#                     logging.info("Validated Data with Pydantic")
#                 except ValidationError as e:
#                     logger.error("Validation error: %s", e)
#                     raise
#             elif menu == "enter_text":
#                 menu_object = QuestionCreatePromptTemplate()

#                 logging.info("Question Generator text Object Created")
#                 try:
#                     validated_data = TranslationInput(**input_data)

#                     logging.info("Validated Data with Pydantic")
#                 except ValidationError as e:
#                     logger.error("Validation error: %s", e)
#                     raise
#             elif menu == "similarQuestion":
#                 menu_object=SimilarQuestionCreatePromptTemplate()
#                 logging.info("Question Generator text Object Created")
#                 try:
#                     validated_data = TranslationInput(**input_data)

#                     logging.info("Validated Data with Pydantic")
#                 except ValidationError as e:
#                     logger.error("Validation error: %s", e)
#                     raise
#             elif menu == "topic":
#                 menu_object=TopicBasedQuestionCreatePromptTemplate()
#                 logging.info("Question Generator text Object Created")
#                 try:
#                     validated_data = TranslationInput(**input_data)

#                     logging.info("Validated Data with Pydantic")
#                 except ValidationError as e:
#                     logger.error("Validation error: %s", e)
#                     raise


#             else:
#                 raise ValueError("Unsupported menu type")

#             promptobject = menu_object.create_prompttemplate(validated_data.dict())
#             logging.info("Prompt Created")

#             # Get the AI model to use
#             # model_object = ChatOpenAIModel()
#             if model_dict["model"] == "gpt-3.5-turbo" or model_dict["model"] == "gpt-4-1106-preview" :
#                 model_object = ChatOpenAIModel()
#                 logging.info("ChatOpenAI Object Created")
#                 model = model_object.create_model(model_dict)
#                 logging.info("Model Created")

#                 # Get chain object
#                 chain = promptobject | model
#                 logging.info("Chain Created")

#                 # Get the response by calling LCEL methods
# response_content, cost = await self.prompt_response.get_response(chain,
# validated_data)

#                 logging.info("Response received")
#                 print("--------------")
#                 print(response_content)
#                 print("--------------")
#                 if menu == "write_email" or menu=="entity" or menu=="enter_text" or menu== "similarQuestion" or menu=='topic':
#                     validate_content=response_content,cost

#                 else:
#                     validate_content = json_validate(response_content, cost)


#                 return validate_content

#             else:
#                 logging.info(model_dict)
#                 model_object = TogetherAIModel()
#                 logging.info("TogetherAI Object Created")
#                 model = model_object.create_model(model_dict)
#                 logging.info("TogetherAI Model Created")

#                 # Manually create the prompt using the prompt template
#                 chain = promptobject | model

#                 # prompt="""what is binary tree"""
#                 logging.info("Prompt Created")
#                 print(chain)

#                 # Invoke the Together model with the generated prompt
#                 response_content,_= await self.prompt_response.get_response(chain, validated_data)
#                 logging.info("Response received")
#                 print("----------")
#                 print(response_content)

#                 # validate_content = json_validate(response_content, cost)
#                 print("============================")

#                 return response_content


#         except Exception as e:
#             logger.exception("Exception in async_pipeline_process: %s", e)
#             raise

# async def start_point(menu: str, model_dict: Dict[str, Any], input_dict: Dict[str, Any]) -> str:
#     max_retries = 3  # Set your maximum number of retries
#     retry_delay_seconds = 1  # Set the delay between retries in seconds

#     for retry_count in range(max_retries):
#         try:
#             pipeline = Pipeline()
#             response = await pipeline.async_pipeline_process(menu, model_dict, input_dict)
#             print("hhhhhhhhh")
#             print(type(response))
#             # result = clean_output(response[0].content)


#             if model_dict["model"] == "gpt-3.5-turbo" or model_dict["model"] == "gpt-4-1106-preview" :
#                 if menu=="write_email" or menu=="entity" or menu == "enter_text" or menu== "similarQuestion" or menu=="topic":
#                     print(response)
#                     result=response[0].content
#                     cost = response[1]
#                 else:
#                     result = clean_output(response[0].content)
#                     cost = response[1]
#             else:
#                 result=response
#                 print(result)

#                 cost=0


#             # Log relevant information
#             logger.info("Menu: %s, Cost: %s, Result: %s", menu, cost, result)
#             return result, cost
#         except RetryableException as e:
#             logger.warning("Retrying (attempt %d) due to: %s", retry_count + 1, str(e))
#             await asyncio.sleep(retry_delay_seconds)  # Add delay before retrying if needed
#         except Exception as e:
#             logger.exception("Exception in start_point: %s", e)
#             raise  # Re-raise the exception to be handled by the view

#     # If all retries fail, handle the situation accordingly
#     logger.error("Maximum retries reached. Failed to process.")
#     raise RetryLimitExceededException("Maximum retries reached.")

# class RetryableException(Exception):
#     """Custom exception class for retryable errors."""
#     pass

# class RetryLimitExceededException(Exception):
#     """Custom exception class for exceeding maximum retries."""
#     pass

# import logging
# import asyncio
# import json
# from pathlib import Path
# from typing import Any, Dict

# from pydantic import ValidationError, BaseModel

# from prompts.src.menus.pydantic_translate import TranslationInput, clean_output
# from prompts.src.menus.pydantic_entity import EntityInput, clean_entity_output
# from prompts.src.menus.translate import TranslateCreatePromptTemplate
# from prompts.src.menus.EmailWriter import EmailWriterCreatePromptTemplate
# from prompts.src.menus.Transliteration import TransliterateCreatePromptTemplate
# from prompts.src.menus.EnterText import QuestionCreatePromptTemplate
# from prompts.src.menus.SimilarQuestion import SimilarQuestionCreatePromptTemplate
# from prompts.src.menus.topic import TopicBasedQuestionCreatePromptTemplate
# from prompts.src.menus.Entity import EntityPromptTemplate
# from prompts.src.models.openaimodels import ChatOpenAIModel
# from prompts.src.models.TogetherModels import TogetherAIModel
# from prompts.src.process_prompt import PromptResponse
# from utils.exceptions import RetryableException, RetryLimitExceededException
# from utils.logging_utils import logger
# from validate.jevaluate import json_validate

# # Load model config
# with open(Path(__file__).parent.parent / "model_config.json") as f:
#     MODEL_CONFIG = json.load(f)

# OPENAI_MODELS = MODEL_CONFIG["models"]["OpenAI"]
# TOGETHER_AI_MODELS = [
#     model for provider in MODEL_CONFIG["models"].keys()
#     if provider != "OpenAI" for model in MODEL_CONFIG["models"][provider]
# ]

# class TransliterationInput(BaseModel):
#     text: str
#     source: str
#     destination: str

# class Pipeline:
#     """Pipeline class for handling different AI models and prompts."""

#     def __init__(self):
#         self.prompt_response = PromptResponse()

#     def _is_openai_model(self, model_name: str) -> bool:
#         return model_name in OPENAI_MODELS

#     def _get_model_pricing(self, model_name: str) -> tuple:
#         """Get pricing information for a model."""
#         for provider in MODEL_CONFIG["pricing"]:
#             if model_name in MODEL_CONFIG["pricing"][provider]:
#                 pricing = MODEL_CONFIG["pricing"][provider][model_name]
#                 return pricing["input"] / 1_000_000, pricing["output"] / 1_000_000
#         return 0.0, 0.0  # Default to free if not found

#     async def async_pipeline_process(self, menu: str, model_dict: dict, input_data: dict) -> tuple:
#         logging.basicConfig(
#             filename="prompts/app.log",
#             level=logging.INFO,
#             filemode="w",
#             format="%(name)s - %(levelname)s - %(message)s",
#         )

#         try:
#             # Validate input data and create the prompt
#             if menu == "translate":
#                 menu_object = TranslateCreatePromptTemplate()
#                 logging.info("Translate Object Created")
#                 validated_data = TranslationInput(**input_data)
#             elif menu == "transliterate":
#                 menu_object = TransliterateCreatePromptTemplate()
#                 logging.info("Transliterate Object Created")
#                 validated_data = TranslationInput(**input_data)
#             elif menu == "entity":
#                 menu_object = EntityPromptTemplate()
#                 logging.info("Entity Recognizer Object Created")
#                 validated_data = TranslationInput(**input_data)
#             elif menu == "write_email":
#                 menu_object = EmailWriterCreatePromptTemplate()
#                 logging.info("EmailWriter Object Created")
#                 validated_data = TranslationInput(**input_data)
#             elif menu == "enter_text":
#                 menu_object = QuestionCreatePromptTemplate()
#                 logging.info("Question Generator text Object Created")
#                 validated_data = TranslationInput(**input_data)
#             elif menu == "similarQuestion":
#                 menu_object = SimilarQuestionCreatePromptTemplate()
#                 logging.info("Question Generator text Object Created")
#                 validated_data = TranslationInput(**input_data)
#             elif menu == "topic":
#                 menu_object = TopicBasedQuestionCreatePromptTemplate()
#                 logging.info("Question Generator text Object Created")
#                 validated_data = TranslationInput(**input_data)
#             else:
#                 raise ValueError("Unsupported menu type")

#             promptobject = menu_object.create_prompttemplate(validated_data.dict())
#             logging.info("Prompt Created")

#             if self._is_openai_model(model_dict["model"]):
#                 model_object = ChatOpenAIModel()
#                 logging.info("ChatOpenAI Object Created")
#                 model = model_object.create_model(model_dict)
#                 logging.info("Model Created")

#                 chain = promptobject | model
#                 logging.info("Chain Created")

#                 response_content, cost = await self.prompt_response.get_response(chain, validated_data)
#                 logging.info("Response received")

#                 if menu not in ["write_email", "entity", "enter_text", "similarQuestion", "topic"]:
#                     validate_content = json_validate(response_content, cost)
#                 else:
#                     validate_content = response_content, cost

#                 return validate_content
#             # In the Together AI model processing section of async_pipeline_process():
# # In the Together AI model processing section of async_pipeline_process():
#             # In the Together AI model processing section:
# else:
#     model_object = TogetherAIModel()
#     logging.info("TogetherAI Object Created")
#     model = model_object.create_model(model_dict)
#     logging.info("TogetherAI Model Created")

#     chain = promptobject | model
#     logging.info("Prompt Created")

#     try:
#         # Get the raw response
#         response = await chain.ainvoke(validated_data.dict())

#         # Debug output
#         print(f"DEBUG - Raw Together AI response: {response}")
#         logger.info(f"Raw Together AI response: {response}")

#         # Initialize values
#         response_content = str(response)
#         prompt_tokens = 0
#         completion_tokens = 0

#         # Try to parse the JSON response if it looks like JSON
#         if response_content.startswith('{') and response_content.endswith('}'):
#             try:
#                 response_json = json.loads(response_content)
#                 if isinstance(response_json, dict):
#                     response_content = response_json.get('output', response_content)
#             except json.JSONDecodeError:
#                 pass

#         # Calculate token counts (fallback method)
#         try:
#             # Simple estimation - count words and multiply by average tokens per word
#             input_text = validated_data.text
#             output_text = response_content

#             # Count words in input and output
#             input_words = len(input_text.split())
#             output_words = len(output_text.split())

#             # Estimate tokens (assuming ~1.5 tokens per word)
#             prompt_tokens = int(input_words * 1.5)
#             completion_tokens = int(output_words * 1.5)

#             # Ensure we have at least some tokens
#             prompt_tokens = max(prompt_tokens, 10)  # Minimum 10 tokens for prompt
# completion_tokens = max(completion_tokens, 3)  # Minimum 3 tokens for
# response

#             logger.info(f"Estimated tokens - Input: {input_words} words -> {prompt_tokens} tokens")
#             logger.info(f"Estimated tokens - Output: {output_words} words -> {completion_tokens} tokens")
#         except Exception as e:
#             logger.warning(f"Token estimation failed: {e}")
#             # Default values if estimation fails
#             prompt_tokens = 15
#             completion_tokens = 5

#         # Calculate cost
#         input_cost, output_cost = self._get_model_pricing(model_dict["model"])
#         cost = (prompt_tokens * input_cost) + (completion_tokens * output_cost)
#         cost_breakdown = (
#             f"Estimated Token Usage:\n"
#             f"Prompt Tokens: {prompt_tokens}\n"
#             f"Completion Tokens: {completion_tokens}\n"
#             f"Total Cost (USD): ${cost:.7f}"
#         )
#         logger.info(
#             cost_breakdown
#         )

#         return response_content, cost_breakdown

#     except Exception as e:
#         logger.error(f"Error processing Together AI response: {e}")
#         raise

#         except ValidationError as e:
#             logger.error("Validation error: %s", e)
#             raise
#         except Exception as e:
#             logger.exception("Exception in async_pipeline_process: %s", e)
#             raise

# async def start_point(menu: str, model_dict: Dict[str, Any], input_dict: Dict[str, Any]) -> tuple:
#     max_retries = 3
#     retry_delay_seconds = 1

#     for retry_count in range(max_retries):
#         try:
#             pipeline = Pipeline()
# response, cost = await pipeline.async_pipeline_process(menu, model_dict,
# input_dict)

#             if pipeline._is_openai_model(model_dict["model"]):
#                 if menu in ["write_email", "entity", "enter_text", "similarQuestion", "topic"]:
#                     result = response[0].content
#                     cost = response[1]
#                 else:
#                     result = clean_output(response[0].content)
#                     cost = response[1]
#             else:
#                 result = response
#                 cost = cost

#             logger.info("Menu: %s, Cost: %s, Result: %s", menu, cost, result)
#             return result, cost
#         except RetryableException as e:
#             logger.warning("Retrying (attempt %d) due to: %s", retry_count + 1, str(e))
#             await asyncio.sleep(retry_delay_seconds)
#         except Exception as e:
#             logger.exception("Exception in start_point: %s", e)
#             raise

#     logger.error("Maximum retries reached. Failed to process.")
#     raise RetryLimitExceededException("Maximum retries reached.")

# class RetryableException(Exception):
#     pass

# class RetryLimitExceededException(Exception):
#     pass

import logging
import asyncio
from typing import Any, Dict

from pydantic import ValidationError, BaseModel

from prompts.src.menus.pydantic_translate import TranslationInput
from prompts.src.menus.translate import TranslateCreatePromptTemplate
from prompts.src.menus.EmailWriter import EmailWriterCreatePromptTemplate
from prompts.src.menus.Transliteration import TransliterateCreatePromptTemplate
from prompts.src.menus.EnterText import QuestionCreatePromptTemplate
from prompts.src.menus.SimilarQuestion import (
    SimilarQuestionCreatePromptTemplate,
)
from prompts.src.menus.topic import TopicBasedQuestionCreatePromptTemplate
from prompts.src.menus.Entity import EntityPromptTemplate
# from prompts.src.process_prompt import PromptResponse
from utils.exceptions import RetryableException, RetryLimitExceededException
from utils.logging_utils import logger
from pathlib import Path
import json
from centralised_llm.src.llm_manager import handle_request
# Load model config
with open(Path(__file__).parents[2] / "centralised_llm" / "src" / "config" / "llm_pricing.json") as f:
    MODEL_CONFIG = json.load(f)

OPENAI_MODELS = MODEL_CONFIG["models"]["openai"]
TOGETHER_AI_MODELS = [
    model for provider in MODEL_CONFIG["models"].keys() 
    if provider != "OpenAI" for model in MODEL_CONFIG["models"][provider]
]
MODEL_TO_PROVIDER = {}
for provider, models in MODEL_CONFIG["models"].items():
    for model in models:
        MODEL_TO_PROVIDER[model] = provider

def get_provider_and_model(model_name: str):
    provider = MODEL_TO_PROVIDER.get(model_name)
    if provider is None:
        raise ValueError(f"Model '{model_name}' is not configured in llm_pricing.json. Please add it.")
    return provider, model_name

SUPPORTED_PARAMETERS = {
    "openai": {"temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty", "stop", "model"},
    "meta_llama": {"temperature", "max_tokens", "top_p","model"},
    "deepseek": {"temperature", "max_tokens", "top_p", "model"},
    "qwen": {"temperature", "max_tokens", "top_p", "model"},
    # Add more as needed
}

def filter_parameters(provider, params):
    allowed = SUPPORTED_PARAMETERS.get(provider, set())
    return {k: v for k, v in params.items() if k in allowed}

class TransliterationInput(BaseModel):
    text: str
    source: str
    destination: str


class Pipeline:
    """
    A pipeline class that handles generating prompts, loading models, and
    processing prompts using the loaded models.
    """

    def __init__(self):
        """
        Initializes the pipeline with necessary components for prompt generation,
        model loading, and prompt processing.
        """
        # self.prompt_response = PromptResponse()

    def _is_openai_model(self, model_name: str) -> bool:
        return model_name in OPENAI_MODELS

    def _get_model_pricing(self, model_name: str) -> tuple:
        """Get pricing information for a model."""
        for provider in MODEL_CONFIG["pricing"]:
            if model_name in MODEL_CONFIG["pricing"][provider]:
                pricing = MODEL_CONFIG["pricing"][provider][model_name]
                return pricing["input"], pricing["output"]
        return 0.0, 0.0  # Default to free if not found

    async def async_pipeline_process(
        self, menu: str, model_dict: dict, input_data: dict
    ) -> tuple:
        """
        Processes the entire pipeline from prompt generation to prompt processing and
        returns the response content and cost.

        Args:
            menu (str): The menu configuration string ("translate" or "transliterate").
            model_dict (dict): The model configuration dictionary containing information
            about the model to be loaded.
            input_data (dict): The input dictionary data containing parameters
            for prompt generation.

        Returns:
            tuple[str, float]: A tuple containing the response content and cost.
        """
        # Configure logging
        logging.basicConfig(
            filename="prompts/app.log",
            level=logging.INFO,
            filemode="w",
            format="%(name)s - %(levelname)s - %(message)s",
        )

        try:
            # Validate input data and create the prompt
            if menu == "translate":
                menu_object = TranslateCreatePromptTemplate()
                logging.info("Translate Object Created")
                try:
                    validated_data = TranslationInput(**input_data)
                    logging.info("Validated Data with Pydantic")
                except ValidationError as e:
                    logger.error("Validation error: %s", e)
                    raise
            elif menu == "transliterate":
                menu_object = TransliterateCreatePromptTemplate()
                logging.info("Transliterate Object Created")
                try:
                    validated_data = TranslationInput(**input_data)
                    logging.info("Validated Data with Pydantic")
                except ValidationError as e:
                    logger.error("Validation error: %s", e)
                    raise
            elif menu == "entity":
                menu_object = EntityPromptTemplate()
                logging.info("Entity Recognizer Object Created")
                try:
                    validated_data = TranslationInput(**input_data)
                    logging.info("Validated Data with Pydantic")
                except ValidationError as e:
                    logger.error("Validation error: %s", e)
                    raise
            elif menu == "write_email":

                menu_object = EmailWriterCreatePromptTemplate()

                logging.info("EmailWriter Object Created")
                try:
                    validated_data = TranslationInput(**input_data)

                    logging.info("Validated Data with Pydantic")
                except ValidationError as e:
                    logger.error("Validation error: %s", e)
                    raise
            elif menu == "enter_text":
                menu_object = QuestionCreatePromptTemplate()

                logging.info("Question Generator text Object Created")
                try:
                    validated_data = TranslationInput(**input_data)

                    logging.info("Validated Data with Pydantic")
                except ValidationError as e:
                    logger.error("Validation error: %s", e)
                    raise
            elif menu == "similarQuestion":
                menu_object = SimilarQuestionCreatePromptTemplate()
                logging.info("Question Generator text Object Created")
                try:
                    validated_data = TranslationInput(**input_data)

                    logging.info("Validated Data with Pydantic")
                except ValidationError as e:
                    logger.error("Validation error: %s", e)
                    raise
            elif menu == "topic":
                menu_object = TopicBasedQuestionCreatePromptTemplate()
                logging.info("Question Generator text Object Created")
                try:
                    validated_data = TranslationInput(**input_data)

                    logging.info("Validated Data with Pydantic")
                except ValidationError as e:
                    logger.error("Validation error: %s", e)
                    raise

            else:
                raise ValueError("Unsupported menu type")

            promptobject = menu_object.create_prompttemplate(
                validated_data.dict()
            )
            logging.info("Prompt Created")
            prompt_string = promptobject.format(**validated_data.dict())
            provider, model_name = get_provider_and_model(model_dict["model"])
            parameters = model_dict.copy()
            parameters["model"] = model_name  # Ensure model name is present
            # Filter out unsupported parameters
            parameters = filter_parameters(provider, parameters)
            print(f"Parameters:{parameters}")
            req1 = json.dumps({
                "model": provider,  # e.g., "openai", "mistralai"
                "prompt": prompt_string,
                "parameters": parameters,
            })
            res = await handle_request(req1)
            # Handle error as string or dict
            if isinstance(res, dict) and res.get("error"):
                logger.error(f"LLM API error: {res['error']}")
                
                return str(res['error']), 0
            elif isinstance(res, str) and res.lower().startswith("error"):
                logger.error(f"LLM API error: {res}")
                return res, 0

            # Normal response handling
            if isinstance(res, dict):
                response_content = res.get("response", "")
                cost_breakdown = res.get("cost", 0)
            else:
                logger.error("Unexpected response type from LLM backend")
                raise RuntimeError("Unexpected response type from LLM backend")
            return response_content, cost_breakdown

            # Get the AI model to use
            # model_object = ChatOpenAIModel()
            # if self._is_openai_model(model_dict["model"]):
            #     model_object = ChatOpenAIModel()
            #     logging.info("ChatOpenAI Object Created")
            #     model = model_object.create_model(model_dict)
            #     logging.info("Model Created")

            #     # Get chain object
            #     chain = promptobject | model
            #     logging.info("Chain Created")

            #     # Get the response by calling LCEL methods
            #     response_content, cost = (
            #         await self.prompt_response.get_response(
            #             chain, validated_data
            #         )
            #     )
            #     if model_dict["model"] in ["gpt-4o-mini"]:
            #         # Extract token usage information from the response
            #         # You might need to adjust this depending on how OpenAI's
            #         # response structure

            #         usage = response_content.response_metadata.get(
            #             "token_usage", {}
            #         )
            #         prompt_tokens = usage.get("prompt_tokens", 0)
            #         completion_tokens = usage.get("completion_tokens", 0)
            #         total_tokens = usage.get(
            #             "total_tokens", prompt_tokens + completion_tokens
            #         )

            #         # Use the same pricing logic as TogetherAI
            #         input_cost, output_cost = self._get_model_pricing(
            #             model_dict["model"]
            #         )
            #         total_cost = (prompt_tokens * input_cost / 1000) + (
            #             completion_tokens * output_cost / 1000
            #         )

            #         cost = (
            #             f"Tokens Used: {total_tokens}\n"
            #             f"Prompt Tokens: {prompt_tokens}\n"
            #             f"Completion Tokens: {completion_tokens}\n"
            #             f"Successful Requests: 1\n"
            #             f"Total Cost (USD): ${total_cost:.7f}"
            #         )

            #     logging.info("Response received")
            #     print("--------------")
            #     print(response_content)
            #     print("--------------")
            #     validate_content = response_content, cost

            #     return validate_content

            # else:
            #     model_object = TogetherAIModel()
            #     logging.info("TogetherAI Object Created")
            #     model = model_object.create_model(model_dict)
            #     logging.info("TogetherAI Model Created")

            #     chain = promptobject | model
            #     logging.info("Prompt Created")

            #     try:
            #         # Get the raw response
            #         response = await chain.ainvoke(validated_data.dict())
            #         logger.info(f"Raw Together AI response: {response}")
            #         print(
            #             "Received Together AI ... Note this actual received response"
            #         )
            #         print(response)

            #         # Extract token usage from response metadata
            #         usage = getattr(
            #             response, "usage_metadata", None
            #         ) or getattr(response, "response_metadata", {}).get(
            #             "token_usage", {}
            #         )

            #         prompt_tokens = usage.get(
            #             "input_tokens", usage.get("prompt_tokens", 0)
            #         )
            #         completion_tokens = usage.get(
            #             "output_tokens", usage.get("completion_tokens", 0)
            #         )
            #         total_tokens = usage.get(
            #             "total_tokens", prompt_tokens + completion_tokens
            #         )

            #         logger.info(
            #             f"Token counts from API: {prompt_tokens} prompt, {completion_tokens} completion"
            #         )

            #         # Get the actual content (handles both string and object
            #         # responses)
            #         response_content = str(
            #             getattr(response, "content", response)
            #         )

            #         # Calculate cost
            #         input_cost, output_cost = self._get_model_pricing(
            #             model_dict["model"]
            #         )
            #         total_cost = (prompt_tokens * input_cost / 1000) + (
            #             completion_tokens * output_cost / 1000
            #         )

            #         cost_breakdown = (
            #             f"Tokens Used: {total_tokens}\n"
            #             f"Prompt Tokens: {prompt_tokens}\n"
            #             f"Completion Tokens: {completion_tokens}\n"
            #             f"Successful Requests: 1\n"
            #             f"Total Cost (USD): ${total_cost:.7f}"
            #         )

            #         logger.info(
            #             f"Together AI Cost Breakdown:\n{cost_breakdown}"
            #         )
                    # if menu == "write_email" or menu=="entity" or menu=="enter_text" or menu== "similarQuestion" or menu=='topic':
                    #     response_content, cost_breakdown=response_content, cost_breakdown

                    # else:
                    #     response_content, cost_breakdown = json_validate(response_content, cost_breakdown)

                #     return response_content, cost_breakdown

                # except Exception as e:
                #     logger.error(f"Error processing Together AI response: {e}")
                #     raise

        except Exception as e:
            logger.exception("Exception in async_pipeline_process: %s", e)
            raise


async def start_point(
    menu: str, model_dict: Dict[str, Any], input_dict: Dict[str, Any]
) -> str:
    max_retries = 3  # Set your maximum number of retries
    retry_delay_seconds = 1  # Set the delay between retries in seconds

    for retry_count in range(max_retries):
        try:
            pipeline = Pipeline()
            response = await pipeline.async_pipeline_process(
                menu, model_dict, input_dict
            )

            # result = clean_output(response[0].content)
            def _is_openai_model(model_name: str) -> bool:
                return model_name in OPENAI_MODELS

            if _is_openai_model(model_dict["model"]):
                if (
                    menu == "write_email"
                    or menu == "entity"
                    or menu == "enter_text"
                    or menu == "similarQuestion"
                    or menu == "topic"
                ):
                    result = response[0]
                    cost = response[1]
                else:
                    result = response[0]
                    cost = response[1]
            else:
                if (
                    menu == "write_email"
                    or menu == "entity"
                    or menu == "enter_text"
                    or menu == "similarQuestion"
                    or menu == "topic"
                ):
                    result = response[0]
                    print(result)

                    cost = response[1]
                else:
                    result = response[0]
                    cost = response[1]

            # Log relevant information
            logger.info("Menu: %s, Cost: %s, Result: %s", menu, cost, result)
            return result, cost
        except RetryableException as e:
            logger.warning(
                "Retrying (attempt %d) due to: %s", retry_count + 1, str(e)
            )
            # Add delay before retrying if needed
            await asyncio.sleep(retry_delay_seconds)
        except Exception as e:
            logger.exception("Exception in start_point: %s", e)
            raise  # Re-raise the exception to be handled by the view

    # If all retries fail, handle the situation accordingly
    logger.error("Maximum retries reached. Failed to process.")
    raise RetryLimitExceededException("Maximum retries reached.")


class RetryableException(Exception):
    """Custom exception class for retryable errors."""


class RetryLimitExceededException(Exception):
    """Custom exception class for exceeding maximum retries."""
