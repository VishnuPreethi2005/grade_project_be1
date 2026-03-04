# from langchain_core.prompts import (ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate)
# from .pydantic_translate import PromptString

# class EmailWriterCreatePromptTemplate:
#     """
#     Class for creating prompt template for email writing tasks.
#     """

#     def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
#         """
# Generates a prompt template for composing an email based on the
# specified type, tone, recipient, purpose, and content.

#         :param input_data: The input dictionary data containing the email details.
#         :returns: The prompt template object.
#         """
#         try:
#             # Basic Prompt
#             PromptString.system_template = (
#                 "Compose an email based on the following details:"
#             )
#             PromptString.email_details = (
#                 "Type of Mail: {type_of_mail}, "
#                 "Tone: {tone}, "
#                 "Recipient: {recipient}, "
#                 "Purpose: {purpose}, "
#                 "Content: {content}"
#             )
#             PromptString.output_format = (

#                  "The content of the email should meet the following criteria:\n"
#     "- It should include a subject line.\n"
#     "- It should address the receiver by name.\n"
#     "- The email should have a clear introduction, body, and conclusion.\n"
#     "- It should be free of grammatical and spelling errors.\n"
#     "- Ensure the email is well-structured and easy to read.\n"
#     "- Include a proper closing statement and the sender's name.\n"
#     "- Make sure the email serves its intended purpose effectively."

#             )


#             # Create chat template with messages
#             chat_template = ChatPromptTemplate.from_messages(
#                 [
#                     SystemMessagePromptTemplate.from_template(
#                         PromptString.system_template
#                     ),
#                     HumanMessagePromptTemplate.from_template(
#                         " ".join([PromptString.email_details, PromptString.output_format])
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
from .pydantic_translate import PromptString


class EmailWriterCreatePromptTemplate:
    """
    Class for creating professional prompt templates for email composition tasks.
    """

    def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
        """
        Generates a structured prompt template for composing professional emails based on
        specified parameters.

        :param input_data: Dictionary containing email details (type_of_mail, tone, recipient, purpose, content)
        :returns: ChatPromptTemplate object ready for use with LLMs
        """
        try:
            # System prompt that sets the context and expectations
            PromptString.system_template = (
                "You are an expert email composer with extensive experience in professional communication. "
                "Your task is to craft a well-structured, compelling email that achieves its intended purpose "
                "while maintaining the appropriate tone and following best practices in business communication."
            )

            # Human message template with detailed instructions
            PromptString.email_details = (
                "Please compose a professional email with the following specifications:\n\n"
                "EMAIL TYPE: {type_of_mail}\n"
                "TONE: {tone}\n"
                "RECIPIENT: {recipient}\n"
                "PURPOSE: {purpose}\n"
                "KEY POINTS TO INCLUDE: {content}\n\n"
            )

            # Output format instructions
            PromptString.output_format = (
                "FORMATTING REQUIREMENTS:\n"
                "1. Include a clear, concise subject line that captures the email's purpose\n"
                "2. Address the recipient appropriately (using their name and title if provided)\n"
                "3. Start with a professional greeting and a brief contextual introduction\n"
                "4. Structure the body with logical paragraphs and include all key points\n"
                "5. Use appropriate transition phrases between sections\n"
                "6. Conclude with a clear next step or call to action\n"
                "7. Add a professional closing and signature\n"
                "8. Ensure the email maintains the requested tone throughout\n\n"
                "Please format your response as a complete email, including subject line, greeting, body, and closing."
            )

            # Create chat template with system and human messages
            chat_template = ChatPromptTemplate.from_messages(
                [
                    SystemMessagePromptTemplate.from_template(
                        PromptString.system_template
                    ),
                    HumanMessagePromptTemplate.from_template(
                        PromptString.email_details + PromptString.output_format
                    ),
                ],
            )

            return chat_template
        except Exception as e:
            print(f"Error occurred during prompt template creation: {e}")
            return None
