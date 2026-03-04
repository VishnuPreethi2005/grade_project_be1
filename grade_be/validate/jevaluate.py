from langchain.evaluation.parsing.base import JsonValidityEvaluator
from rest_framework.response import Response
import json

"""
Validate the JSON response content.

This function validates the JSON response content received from an API endpoint.

Parameters:
    response_content (Response): The response content received from the API endpoint.
    cost (float): The cost associated with the response.

Returns:
    tuple: A tuple containing the validated response content and the associated cost.

Global Variables:
    language_keys (list): A global list used to store language keys extracted from valid JSON responses.

Dependencies:
    This function depends on the langchain.evaluation.parsing.base.JsonValidityEvaluator class for evaluating JSON validity.
    It also imports the Response class from the rest_framework.response module and the json module for JSON parsing.

Algorithm:
    1. Evaluate the validity of the JSON response using the JsonValidityEvaluator class.
    2. If the JSON response is valid:
        - Parse the JSON content to extract language keys.
        - Add the language keys to the global language_keys list.
        - Return the validated response content and the associated cost.
    3. If the JSON response is invalid:
        - Return a Response object with an error message indicating the invalidity and reasoning.

Example:
    response, cost = json_validate(response_content, 10.0)
"""


language_keys = []


def json_validate(response_content, cost):

    global language_keys

    json_validity_evaluator = JsonValidityEvaluator()
    evaluation_result = json_validity_evaluator.evaluate_strings(
        prediction=response_content.content
    )
    print("------------------------------", evaluation_result)

    if evaluation_result["score"] == 1:

        dist = json.loads(response_content.content)
        # Separate keys and values
        language = list(dist.keys())
        language_keys.extend((language))

        return response_content, cost

    else:
        print("Invalid")
        return (
            Response(
                {
                    "error": "JSON validation failed",
                    "original_response": response_content.content,
                },
                status=500,
            ),
            cost,
        )
