import pytest
from rest_framework.test import APIClient
from unittest.mock import patch, MagicMock


@pytest.mark.django_db
@patch("executor.question_generator.generate_with_fallbacks")
@patch("executor.question_generator.model.encode")
@patch("sentence_transformers.util.cos_sim")
def test_generate_question_flow_success(mock_cos_sim, mock_encode, mock_generate):
    mock_generate.return_value = '''[
        {
            "title": "Add Two Numbers",
            "description": "Write a function to add two integers.",
            "sample_io": [{"input": "1 2", "output": "3"}],
            "explanation": "Add and return the sum.",
            "constraints": "1 <= a, b <= 1000",
            "testcase_description": "Simple addition test",
            "topics": ["Math"],
            "companies_asked": ["Google"],
            "test_cases": [{"input": "3 5", "output": "8"}]
        }
    ]'''

    mock_encode.return_value = MagicMock()
    mock_cos_sim.return_value.max.return_value.item.return_value = 0.1

    client = APIClient()
    payload = {
        "topic": "Math",
        "difficulty": "Easy"
    }

    response = client.post("/api/generate_questions/", payload, format="json")

    assert response.status_code == 201
    assert "Add Two Numbers" in response.content.decode()
