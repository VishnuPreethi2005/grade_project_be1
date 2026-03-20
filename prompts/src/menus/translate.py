"""
Writing the Prompt to Translate
"""

from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)

from .pydantic_translate import PromptString


class TranslateCreatePromptTemplate:
    """
    Class for creating prompt template for translation tasks.
    """

    def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
        """
        Generates a prompt template for translating the specified text from source to
        the given destination language.

        :param input_data: The input dictionary data containing:
            - source: source language
            - destination: target language(s)
            - text: text to translate
            - domain: optional domain context
            - subdomain: optional subdomain context
        :returns: The prompt template object.
        """
        try:
            # System prompt
            PromptString.system_template = (
                "You are a professional translation expert with deep knowledge of linguistic nuances. "
                "Your task is to provide accurate, natural translations that maintain the original meaning "
                "while adapting to the target language's cultural context."
            )

            # Human message template
            PromptString.text_to_translate = (
                "TRANSLATION REQUEST:\n"
                "Source Language: {source}\n"
                "Target Language(s): {destination}\n"
                "Text to Translate: {text}\n\n"
            )

            # Context templates
            PromptString.template_full = (
                "DOMAIN CONTEXT:\n"
                "Domain: {domain}\n"
                "Subdomain: {subdomain}\n\n"
            )
            PromptString.template_domain = (
                "DOMAIN CONTEXT:\n" "Domain: {domain}\n\n"
            )
            PromptString.template_subdomain = (
                "DOMAIN CONTEXT:\n" "Subdomain: {subdomain}\n\n"
            )

            # Output format instructions
            PromptString.output_format = (
                "OUTPUT REQUIREMENTS:\n"
                "1. For each target language, show the language name followed by the translation\n"
                "2. Format as: '[Language Name]:\\n[Translated Text]\\n\\n'\n"
                "3. Do not include any JSON formatting, brackets, or technical notation\n"
                "4. Ensure translations are natural and idiomatic\n"
                "5. Maintain any specialized terminology when domain/subdomain is specified\n"
                "6. Do not include additional explanations or notes\n\n"
                "Example output format:\n"
                "Spanish:\n"
                "Este es el texto traducido al español.\n\n"
                "French:\n"
                "Ceci est le texte traduit en français.\n\n"
            )

            # Build context template based on provided information
            if (
                len(input_data["domain"]) != 0
                and len(input_data["subdomain"]) != 0
            ):
                PromptString.context_template = PromptString.template_full
            elif len(input_data["domain"]) != 0:
                PromptString.context_template = PromptString.template_domain
            elif len(input_data["subdomain"]) != 0:
                PromptString.context_template = PromptString.template_subdomain
            else:
                PromptString.context_template = ""

            # Create chat template
            chat_template = ChatPromptTemplate.from_messages(
                [
                    SystemMessagePromptTemplate.from_template(
                        PromptString.system_template
                    ),
                    HumanMessagePromptTemplate.from_template(
                        PromptString.text_to_translate
                        + PromptString.context_template
                        + PromptString.output_format
                    ),
                ],
            )
            return chat_template
        except Exception as e:
            print(f"Error occurred during prompt creation: {e}")
            return None
