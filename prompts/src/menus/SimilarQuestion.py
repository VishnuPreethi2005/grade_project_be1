from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from typing import Dict, Any, Optional, List


# This file may also need Pydantic models if used for parsing
from pydantic import BaseModel
class QuestionOutput(BaseModel):
    question: str
    answer: Optional[str] = None
    explanation: Optional[str] = None
    
class QuestionOutputList(BaseModel):
    items: List[QuestionOutput]


def get_option_example(option_type: str, num_options: int) -> Dict[str, str]:
    """
    Generates an example string for MCQ options and a sample answer format.
    
    :param option_type: The style of options (e.g., "numerical", "alphabetical", "alphabetical_uppercase", "roman_numerals").
    :param num_options: The number of options to generate.
    :returns: A dictionary with 'example_string' and 'sample_answer'.
    """
    options = []
    sample_answer = ""
    
    if option_type == "numerical":
        # e.g., 1) Option 1, 2) Option 2
        options = [f"   {i+1}) [Option {i+1}]" for i in range(num_options)]
        sample_answer = "e.g., '2'"
    
    elif option_type == "roman_numerals":
        # e.g., I) Option 1, II) Option 2
        roman_map = {
            1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 
            6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X",
        }
        options = [
            f"   {roman_map.get(i+1, str(i+1))}) [Option {i+1}]"
            for i in range(num_options)
        ]
        sample_answer = "e.g., 'II'"
        
    elif option_type == "alphabetical_lowercase":
        # e.g., a) Option 1, b) Option 2
        options = [f"   {chr(97 + i)}) [Option {i+1}]" for i in range(num_options)]  # 97 is 'a'
        sample_answer = "e.g., 'b'"
        
    else:  # Default to uppercase alphabetical (for 'alphabetical' or any other value)
        # e.g., A) Option 1, B) Option 2
        options = [f"   {chr(65 + i)}) [Option {i+1}]" for i in range(num_options)]  # 65 is 'A'
        sample_answer = "e.g., 'B'"

    return {
        "example_string": "\n".join(options),
        "sample_answer": sample_answer,
    }


class SimilarQuestionCreatePromptTemplate:
    """
    Class for creating optimized prompt templates for generating similar questions.
    Strictly follows all parameters and provides perfect formatting for each question type.
    """

    def create_prompttemplate(self, input_data: dict) -> ChatPromptTemplate:
        """
        Generates similar questions with strict parameter adherence and perfect formatting.

        :param input_data: Dictionary containing all question generation parameters
        :returns: ChatPromptTemplate object with precise instructions or error message for missing fields
        """
        try:
            # Check if similar_question is provided
            similar_question = input_data.get("similar_question", "")
            if not similar_question or similar_question.strip() == "":
                # Return a template that asks for a similar question
                return ChatPromptTemplate.from_messages(
                    [
                        SystemMessagePromptTemplate.from_template(
                            "You are a helpful question generation assistant."
                        ),
                        HumanMessagePromptTemplate.from_template(
                            "Please provide a similar question as reference to generate new questions. "
                            "Without a reference question, I cannot create properly formatted similar questions."
                        ),
                    ]
                )

            # Extract key parameters with defaults
            provide_answer = input_data.get("provideAnswerValue", "Yes")
            explanation_detail = input_data.get(
                "explanationValue", "Not required"
            )
            question_type = input_data.get(
                "questionType", "Short-answer Questions"
            )
            input_data.get("formatValue", "Structured")
            
            # Get dynamic option examples
            num_options = int(input_data.get("numberOfOptionsValue", 4))
            # Default to 'alphabetical' (Uppercase)
            raw_option_type_value = input_data.get("optionTypeValue", "alphabetical").strip()

            # Normalize UI labels to backend types
            if "1" in raw_option_type_value:
                option_type = "numerical"
            elif "II" in raw_option_type_value or "roman" in raw_option_type_value.lower():
                option_type = "roman_numerals"
            elif "a" in raw_option_type_value and "b" in raw_option_type_value and raw_option_type_value.islower():
                option_type = "alphabetical_lowercase"
            elif "A" in raw_option_type_value and "B" in raw_option_type_value and raw_option_type_value.isupper():
                option_type = "alphabetical"
            else:
                # Default to alphabetical (uppercase) if no other type matches
                option_type = "alphabetical"
            option_example_data = get_option_example(option_type, num_options)
            option_example_string = option_example_data["example_string"]
            sample_answer_format = option_example_data["sample_answer"]

            option_type_description = ""
            if option_type == "numerical":
                option_type_description = "numerical"
            elif option_type == "roman_numerals":
                option_type_description = "roman numeral"
            elif option_type == "alphabetical_lowercase":
                option_type_description = "lowercase alphabetical"
            else: # "alphabetical" or any other value
                option_type_description = "uppercase alphabetical"

            # System prompt with strict instructions
            raw_num_missing_words = input_data.get("numberOfMissingWordsValue")
            try:
                num_missing_words = int(raw_num_missing_words) if raw_num_missing_words is not None else 1
            except ValueError:
                num_missing_words = 1 # Default to 1 if conversion fails

            system_template = (
                "You are an expert educational question generator specialized in creating similar questions. Strictly follow these rules:\n"
                "1. Generate exactly {numQuestionsValue} questions — ALL must be of type: '{questionType}'. Do NOT mix question types under any circumstance.\n"
                f"2. For 'Fill in the blanks' questions, ensure exactly {num_missing_words} blanks are present.\n"
                "3. Base questions on the same pattern as: {similar_question}\n"
                "4. Provide Answer: {provideAnswerValue}\n"
                "5. Explanation: {explanationValue}\n"
                + (f"   - If explanation is required, ensure it is exactly {explanation_detail} long." if "sentence" in explanation_detail.lower() else "") + "\n"
                "6. Format output as: {formatValue}\n"
                "7. Never deviate from specified parameters\n"
                "8. For each question type, provide appropriate answer format (not just Yes/No)\n"
                + (f"9. For MCQ questions, strictly generate options *exactly* as demonstrated in the FORMAT EXAMPLE, using the {option_type_description} style (e.g., A, B, C or 1, 2, 3 or I, II, III or a, b, c) and preserving the exact casing/numbering for options." if question_type == 'MCQ' else "")
            )

            # Define type-specific answer formats
            answer_formats = {
                "MCQ": f"   Answer: [Correct option letter/number, {sample_answer_format}]\n",
                "Fill in the blanks": "   Answer: [Correct word(s) to fill in the blank(s)]\n",
                "Match the following": "   Answer: a-ii, b-i, c-iv, etc.\n",
                "True/False": "   Answer: [True or False]\n",
                "Short-answer Questions": "   Answer: [Brief, specific answer to the question]\n",
                "Essay Questions": "   Answer: [Key points expected in the essay]\n",
                "Numerical Problems": "   Answer: [Numerical solution with step-by-step calculation]\n",
                "Programming Exercise": "   Answer: [Code solution, e.g.:\n```python\ndef add_numbers(a, b):\n    return a + b\n```]\n",
            }

            # Get the appropriate answer format for the question type
            answer_format = answer_formats.get(
                question_type,
                "   Answer: [Appropriate answer for the question]\n",
            )

            # Prepare answer section based on parameters
            answer_section = ""
            if provide_answer == "Yes":
                answer_section = answer_format
                if explanation_detail != "Not required":
                    answer_section += f"   Explanation: [Provide {explanation_detail} explanation]\n"

            # Enhanced type-specific requirements with perfect formatting
            type_specific = {
                "MCQ": (
                    "Options: {numberOfOptionsValue} ({optionTypeValue} style)\n"
                    "FORMAT EXAMPLE (follow EXACTLY this option style, including casing):\n"
                    "1. [Clear question stem]\n"
                    "   {option_example_string}\n"
                    "IMPORTANT: Do NOT use any other format (e.g., if shown as 'a)', do not write 'A)'; if shown as '1)', do not use letters).\n"
                    f"{answer_section}"
                ),
                "Fill in the blanks": (
                    "Missing Words: {numberOfMissingWordsValue} (shown as {representingWordsValue})\n"
                    "FORMAT EXAMPLE:\n"
                    "1. [Sentence from passage with {representingWordsValue} for missing words].\n"
                    "{answer_section}"
                ),
                "Match the following": (
                    "Items: {numberOfItemsValue} pairs per question\n"
                    "PERFECT FORMAT:\n"
                    "1. Match the following:\n"
                    "   Column A\t\tColumn B\n"
                    "   a. [Item 1]\t\ti. [Match 1]\n"
                    "   b. [Item 2]\t\tii. [Match 2]\n"
                    "   ...\n"
                    "{answer_section}\n\n"
                ),
                "True/False": (
                    "FORMAT EXAMPLE:\n"
                    "1. Paris is the capital of France. (True/False)\n"
                    "{answer_section}"
                ),
                "Short-answer Questions": (
                    "FORMAT EXAMPLE:\n"
                    "1. What is the capital of France?\n"
                    "{answer_section}"
                ),
                "Essay Questions": (
                    "FORMAT EXAMPLE:\n"
                    "1. Discuss the cultural significance of Paris as France's capital.\n"
                    "   Expected length: {essayLengthValue}\n"
                    "{answer_section}"
                ),
                "Numerical Problems": (
                    "FORMAT EXAMPLE:\n"
                    "1. If x = 2 and y = 3, what is x + y?\n"
                    "{answer_section}"
                ),
                "Programming Exercise": (
                    "FORMAT EXAMPLE:\n"
                    "1. Write a Python function to add two numbers.\n"
                    "{answer_section}"
                ),
            }

            type_req = type_specific.get(
                question_type,
                "Format each question clearly with question number.",
            ).format(
                answer_section=answer_section,
                option_example_string=option_example_string,
                essayLengthValue=input_data.get(
                    "essayLengthValue", "3-5 paragraphs"
                ),
                numberOfOptionsValue=num_options,
                optionTypeValue=option_type,
                numberOfMissingWordsValue=input_data.get(
                    "numberOfMissingWordsValue"
                ),
                representingWordsValue=input_data.get(
                    "representingWordsValue", "blanks"
                ),
                numberOfItemsValue=input_data.get("numberOfItemsValue", "5"),
            )

            # Human message template with strict formatting
            similar_question_template = (
                "SIMILAR QUESTION REFERENCE:\n{similar_question}\n\n"
                "QUESTION REQUIREMENTS:\n"
                "Type: {questionType}\n"
                "Bloom's Level: {bloomValue}\n"
                "Difficulty: {levelValue}\n"
                "Learning Objective: {learningObj}\n"
                "{type_specific_requirements}\n\n"
                "Generate exactly {numQuestionsValue} new question(s) following the pattern of the similar question."
            )

            # Final output format instructions
            output_format = (
                "STRICT OUTPUT RULES:\n"
                "1. Provide Answer: "
                + (
                    "Yes - include APPROPRIATE answers for each question type (not just Yes/No)"
                    if provide_answer == "Yes"
                    else "No - do not include answers"
                )
                + "\n"
                "2. Explanation: "
                + (
                    explanation_detail
                    if explanation_detail != "Not required"
                    else "Not required - do not include explanations"
                )
                + "\n"
                "3. Maintain perfect formatting for {questionType}\n"
                "4. Number all questions sequentially starting from 1\n"
                "5. Ensure questions follow the same pattern as the provided similar question\n"
                "6. Match the specified difficulty ({levelValue}) and Bloom's level ({bloomValue})\n"
                "7. For each question type, the answer must be relevant and appropriate (as shown in FORMAT EXAMPLE):\n"
                f"   - MCQ: Specify the correct option ({sample_answer_format})\n"
                "   - Fill in the blanks: Provide the missing word(s)\n"
                "   - Match the following: Show which items match (e.g., a-ii, b-i)\n"
                "   - True/False: State True or False\n"
                "   - Short-answer: Give a concise, specific answer\n"
                "   - Essay Questions: Provide key points expected in the answer\n"
                "   - Numerical Problems: Show the numerical answer with workings\n"
                "   - Programming Exercise: Include the actual code solution"
            )

            chat_template = ChatPromptTemplate.from_messages(
                [
                    SystemMessagePromptTemplate.from_template(system_template),
                    HumanMessagePromptTemplate.from_template(
                        similar_question_template.format(
                            type_specific_requirements=type_req, **input_data
                        )
                        + "\n\n"
                        + output_format.format(**input_data)
                    ),
                ],
            )
            return chat_template

        except Exception as e:
            print(f"Prompt creation error: {e}")
            return None