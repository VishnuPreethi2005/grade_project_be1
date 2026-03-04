import pytest
from unittest.mock import patch, MagicMock
from rest_framework.test import APIRequestFactory
from rest_framework.request import Request
from rest_framework.parsers import JSONParser
from rest_framework.negotiation import DefaultContentNegotiation
from executor.question_generator import generate_questions_logic

@pytest.mark.django_db
@patch("sentence_transformers.util.cos_sim")
@patch("executor.question_generator.model.encode")
@patch("executor.question_generator.generate_with_fallbacks")
def test_generate_questions_logic_success(mock_generate, mock_encode, mock_cos_sim):
    mock_generate.return_value = """
    [
        {
            "title": "Sum of Two Numbers",
            "description": "Given two numbers, return their sum.",
            "sample_io": [{"input": "2 3", "output": "5"}],
            "explanation": "Simple addition",
            "constraints": "1 <= a, b <= 1000",
            "testcase_description": "Test basic addition",
            "topics": ["Math"],
            "companies_asked": ["Google"],
            "test_cases": [{"input": "10 20", "output": "30"}]
        }
    ]
    """
    mock_encode.return_value = MagicMock()
    mock_cos_sim.return_value.max.return_value.item.return_value = 0.1  # Not duplicate

    factory = APIRequestFactory()
    request = factory.post("/generate-questions", {
        "topic": "Math",
        "difficulty": "Easy"
    }, format='json')

    # ✅ Fix: Wrap in DRF Request and set parser + negotiator
    drf_request = Request(request)
    drf_request.parsers = [JSONParser()]
    drf_request.negotiator = DefaultContentNegotiation()

    response = generate_questions_logic(drf_request)

    assert response.status_code == 201
    data = response.data
    assert "questions" in data
    assert len(data["questions"]) > 0
    assert data["questions"][0]["title"] == "Sum of Two Numbers"
