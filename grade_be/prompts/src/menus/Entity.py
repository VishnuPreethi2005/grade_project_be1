# from langchain_core.prompts import (ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate)
# from .pydantic_entity import EntityPromptString

# class EntityPromptTemplate:
#     """
#     Class for creating prompt template for entity tasks.
#     """

#     def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
#         """
# Generates a prompt template for identifying entities in the specified
# text.

#         :param input_data: The input dictionary data containing the text and entity details.
#         :returns: The prompt template object.
#         """
#         try:
#             # System prompt
#             EntityPromptString.system_template = (
#                 "You are an expert in named entity recognition. "
#                 "Your task is to identify and extract entities from the given text "
#                 "and present them in a clean, readable format suitable for direct display."
#             )

#             # Human message template
#             EntityPromptString.text_to_analyze = (
#                 "Please analyze the following text and identify the specified entities:\n\n"
#                 "TEXT TO ANALYZE: {text}\n"
#                 "ENTITY TYPES TO IDENTIFY: {Entity}\n"
#                 "CUSTOM ENTITY TYPES (if any): {CustomEntity}\n\n"
#             )

#             # Output format instructions
#             EntityPromptString.output_format = (
#                 "FORMATTING REQUIREMENTS:\n"
#                 "1. List each entity you find on a new line\n"
#                 "2. Format each entry as: 'Entity Type: Entity Name'\n"
#                 "3. For named entities, include the specific type (e.g., 'Person: John Doe')\n"
#                 "4. Do not include any JSON formatting, brackets, or other technical notation\n"
#                 "5. If no entities are found, simply state 'No entities found in the text'\n"
#                 "6. Ensure the output is clean and ready for direct display in a user interface\n\n"
#                 "Example output format:\n"
#                 "Person: John Smith\n"
#                 "Organization: Acme Corporation\n"
#                 "Location: New York"
#             )

#             # Create chat template with messages
#             chat_template = ChatPromptTemplate.from_messages(
#                 [
#                     SystemMessagePromptTemplate.from_template(
#                         EntityPromptString.system_template
#                     ),
#                     HumanMessagePromptTemplate.from_template(
#                         EntityPromptString.text_to_analyze + EntityPromptString.output_format
#                     ),
#                 ],
#             )

#             return chat_template
#         except Exception as e:
#             print(f"Error occurred during prompt creation: {e}")
#             return None

# from langchain_core.prompts import (ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate)
# from .pydantic_entity import EntityPromptString

# class EntityPromptTemplate:
#     """
#     Class for creating prompt template for entity tasks.
#     """

#     def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
#         """
# Generates a prompt template for identifying entities in the specified
# text.

#         :param input_data: The input dictionary data containing the text and entity details.
#         :returns: The prompt template object.
#         """
#         try:
#             # System prompt
#             EntityPromptString.system_template = (
#                 "You are an expert in named entity recognition. "
#                 "Your task is to identify and extract entities from the given text "
#                 "based on the specific entity types requested."
#             )

#             # Human message template
#             EntityPromptString.text_to_analyze = (
#                 "Please analyze the following text and identify the specified entities:\n\n"
#                 "TEXT TO ANALYZE: {text}\n"
#                 "ENTITY TYPES TO IDENTIFY: {Entity}\n"
#                 "CUSTOM ENTITY TYPES (if any): {CustomEntity}\n\n"
#             )

#             # Output format instructions
#             EntityPromptString.output_format = (
#                 "FORMATTING REQUIREMENTS:\n"
#                 "1. If 'Named Entity Recognition (NER)' is selected, identify all common entity types "
#                 "(Person, Organization, Location, Date, Time, etc.)\n"
#                 "2. If specific entity types are selected (e.g., 'Person', 'Date'), only show those types\n"
#                 "3. Include any custom entity types specified\n"
#                 "4. List each entity you find on a new line\n"
#                 "5. Format each entry as: 'Entity Type: Entity Name'\n"
#                 "6. Do not include any JSON formatting, brackets, or other technical notation\n"
#                 "7. If no entities of the requested types are found, state 'No entities found in the text'\n"
#                 "8. Ensure the output is clean and ready for direct display in a user interface\n\n"
#                 "Example output format:\n"
#                 "Person: John Smith\n"
#                 "Organization: Acme Corporation\n"
#                 "Location: New York"
#             )

#             # Create chat template with messages
#             chat_template = ChatPromptTemplate.from_messages(
#                 [
#                     SystemMessagePromptTemplate.from_template(
#                         EntityPromptString.system_template
#                     ),
#                     HumanMessagePromptTemplate.from_template(
#                         EntityPromptString.text_to_analyze + EntityPromptString.output_format
#                     ),
#                 ],
#             )

#             return chat_template
#         except Exception as e:
#             print(f"Error occurred during prompt creation: {e}")
#             return None
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from .pydantic_entity import EntityPromptString


class EntityPromptTemplate:
    """
    Class for creating prompt template for entity tasks.
    """

    def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
        """
        Generates a prompt template for identifying entities in the specified text.

        :param input_data: The input dictionary data containing the text and entity details.
        :returns: The prompt template object.
        """
        try:
            # System prompt
            EntityPromptString.system_template = (
                "You are an expert in named entity recognition. "
                "Your task is to identify and extract ONLY the specific entity types requested "
                "from the given text, and group them by entity type."
            )

            # Human message template
            EntityPromptString.text_to_analyze = (
                "Please analyze the following text and identify ONLY the specified entities:\n\n"
                "TEXT TO ANALYZE: {text}\n"
                "ENTITY TYPES TO IDENTIFY: {Entity}\n"
                "CUSTOM ENTITY TYPES (if any): {CustomEntity}\n\n"
            )

            # Output format instructions
            EntityPromptString.output_format = (
                "FORMATTING REQUIREMENTS:\n"
                "1. IMPORTANT: ONLY extract entity types that are explicitly requested\n"
                "2. If 'Named Entity Recognition (NER)' is selected, identify all common entity types\n"
                "3. If specific entity types are selected (e.g., only 'Date'), ONLY show those specific types\n"
                "4. Group entities by their types\n"
                "5. Format the output as follows:\n"
                "   - Entity type in uppercase with a colon (e.g., 'DATES:')\n"
                "   - Each entity on a new line with a hyphen prefix (e.g., '- July 2023')\n"
                "   - Empty line between different entity types\n"
                "6. If no entities of the requested types are found, state 'No entities of the requested types found in the text'\n"
                "7. Do NOT include any note about custom entity types unless they were explicitly requested\n"
                "8. Do NOT include entity types that weren't specifically requested\n\n"
                "Example output for when ONLY 'Date' is selected:\n"
                "DATES:\n"
                "- July 2023\n"
                "- September 12, 2023\n\n"
                "Example output for when 'Named Entity Recognition (NER)' is selected:\n"
                "PERSONS:\n"
                "- John Smith\n\n"
                "ORGANIZATIONS:\n"
                "- Acme Corporation\n\n"
                "LOCATIONS:\n"
                "- New York\n\n"
                "DATES:\n"
                "- July 2023"
            )

            # Create chat template with messages
            chat_template = ChatPromptTemplate.from_messages(
                [
                    SystemMessagePromptTemplate.from_template(
                        EntityPromptString.system_template
                    ),
                    HumanMessagePromptTemplate.from_template(
                        EntityPromptString.text_to_analyze
                        + EntityPromptString.output_format
                    ),
                ],
            )

            return chat_template
        except Exception as e:
            print(f"Error occurred during prompt creation: {e}")
            return None
