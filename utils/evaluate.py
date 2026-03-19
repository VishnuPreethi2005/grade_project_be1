from langchain.evaluation import load_evaluator
from validate.jevaluate import language_keys as keys_module


"""
Calculate pairwise distances between translations in a translation history.

This function calculates pairwise distances between translations in a translation history
based on string distances between input texts and responses.

Parameters:
    translation_history (list): A list of tuples containing translation history.
        Each tuple should contain input text and response as (input_text, response).

Returns:
    None

Dependencies:
    This function depends on the langchain.evaluation module for loading the string distance evaluator.
    It also uses the validate.jevaluate.language_keys module for obtaining language keys.

Algorithm:
    1. Load the string distance evaluator.
    2. Ensure there are at least two translations for comparison.
    3. Initialize an empty list to store pairwise distances.
    4. Iterate over translation pairs and calculate distances if keys are the same.
    5. Print the calculated pairwise distances.

Notes:
    - The evaluator is used to calculate string distances between input texts and responses.
    - Pairwise distances are calculated only if the keys (languages) are the same for both translations.
    - If there are insufficient translations for comparison, a message is printed and the function returns.

Example:
    calculate_pairwise_distances([
        ("Hello", "Bonjour"),
        ("Goodbye", "Au revoir"),
        ("Yes", "Oui")
    ])
"""


def calculate_pairwise_distances(translation_history):
    # Load the string distance evaluator
    evaluator = load_evaluator("string_distance")

    # Ensure there are at least two translations for comparison
    if len(translation_history) < 2:
        print("Insufficient data to calculate string distances")
        return

    # Initialize a list to store all pairwise distances
    pairwise_distances = []

    for i in range(len(translation_history)):
        for j in range(i + 1, len(translation_history)):
            input_text_i, response_i = translation_history[i]
            input_text_j, response_j = translation_history[j]

            # Check if keys are the same for the current pair
            keys_i = keys_module[i]
            keys_j = keys_module[j]
            print("key", keys_i)
            print("key", keys_j)

            if keys_i == keys_j:
                # Calculate distance using the evaluator for both input text
                # and response
                input_text_distance = evaluator.evaluate_strings(
                    prediction=input_text_j, reference=input_text_i
                )
                response_distance = evaluator.evaluate_strings(
                    prediction=response_j, reference=response_i
                )

                pairwise_distances.append(
                    {
                        "pair": (i, j),
                        "input_text_distance": input_text_distance,
                        "response_distance": response_distance,
                    }
                )
            else:
                print(f"Keys are different for pair {i} and {j}")

    # Print the calculated pairwise distances
    print("Pairwise Distances:", pairwise_distances)
