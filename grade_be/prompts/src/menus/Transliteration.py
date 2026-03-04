from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from .pydantic_translate import PromptString


class TransliterateCreatePromptTemplate:
    """
    Class for creating prompt template for phonetic transliteration tasks.
    Output format exactly matches translation template style.
    """

    def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
        """
        Generates a prompt template for script-to-script phonetic conversion.

        :param input_data: Dictionary containing:
            - source: Source script/language (e.g., "Devanagari")
            - destination: Target script (e.g., "Latin")
            - text: Text to transliterate (e.g., "नमस्ते")
        :returns: ChatPromptTemplate with pronunciation-focused instructions
        """
        try:
            # System prompt - Phonetic conversion specialist
            PromptString.system_template = (
                "You are a professional phonetic conversion tool. Your ONLY task is to "
                "convert text from {source} script to {destination} script by matching "
                "SOUNDS, NOT meanings. Preserve original pronunciation with 100% accuracy."
            )

            # Human message template
            PromptString.text_to_translate = (
                "PHONETIC CONVERSION REQUEST:\n"
                "Source Script: {source}\n"
                "Target Script: {destination}\n"
                "Original Text: {text}\n\n"
                "CONVERSION RULES:\n"
                "1. Convert CHARACTER-BY-CHARACTER based on SOUND\n"
                "2. NEVER translate meanings\n"
                "3. For multiple scripts, process each separately\n"
                "4. Use standard transliteration schemes (ISO 15919 for Indic, Hepburn for Japanese)\n"
                "5. Preserve capitalization and punctuation\n\n"
            )

            # Output format (EXACTLY matches translation template style)
            PromptString.output_format = (
                "OUTPUT REQUIREMENTS:\n"
                "1. For each target script, show the script name followed by the transliteration\n"
                "2. Format as: '[Script Name]:\\n[Transliterated Text]\\n\\n'\n"
                "3. Do not include any JSON formatting, brackets, or technical notation\n"
                "4. Ensure transliterations match standard phonetic conventions\n"
                "5. Maintain original capitalization and punctuation\n"
                "6. Do not include additional explanations or notes\n\n"
                "Example output format:\n"
                "Latin:\n"
                "namaste\n\n"
                "Cyrillic:\n"
                "намастэ\n\n"
            )

            chat_template = ChatPromptTemplate.from_messages(
                [
                    SystemMessagePromptTemplate.from_template(
                        PromptString.system_template
                    ),
                    HumanMessagePromptTemplate.from_template(
                        PromptString.text_to_translate
                        + PromptString.output_format
                    ),
                ],
            )
            return chat_template
        except Exception as e:
            print(f"Transliteration prompt error: {e}")
            return None
