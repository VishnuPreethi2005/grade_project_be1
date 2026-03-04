import pytest
from unittest.mock import patch
from executor.code_grader import generate_grading_json

@pytest.mark.django_db
@patch("executor.code_grader.generate_with_fallbacks")
@patch("executor.code_grader.build_grading_prompt")
def test_generate_grading_json_success(mock_build_prompt, mock_generate_fallback):
    # Arrange
    sample_code = "print(int(input()) + 1)"
    sample_question = "Given a number, print the number + 1."
    public_testcases = [
        {"input": "2", "expected_output": "3"},
        {"input": "10", "expected_output": "11"}
    ]

    mock_build_prompt.return_value = "MOCK_PROMPT"
    mock_generate_fallback.return_value = {
        "score": 9,
        "feedback": "Correct output for all test cases.",
        "reasoning": "Your code handles the required operation correctly."
    }

    # Act
    result = generate_grading_json(sample_code, sample_question, public_testcases)

    # Assert
    mock_build_prompt.assert_called_once_with(sample_code, sample_question, public_testcases)
    mock_generate_fallback.assert_called_once_with("MOCK_PROMPT")

    assert isinstance(result, dict)
    assert result["score"] == 9
    assert "feedback" in result
