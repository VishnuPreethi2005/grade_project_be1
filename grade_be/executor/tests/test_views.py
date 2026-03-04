import pytest
from rest_framework.test import APIClient
from unittest.mock import patch, MagicMock
from executor.models import Question
import json


@pytest.mark.django_db
def test_list_questions():
    Question.objects.create(title="Test Question", description="Test description")
    client = APIClient()
    response = client.get("/api/questions/")
    assert response.status_code == 200
    assert isinstance(response.data, list)


@pytest.mark.django_db
def test_get_question_found():
    question = Question.objects.create(title="Q1", description="desc")
    client = APIClient()
    response = client.get(f"/api/questions/{question.id}/")
    assert response.status_code == 200
    assert response.data["title"] == "Q1"


@pytest.mark.django_db
def test_get_question_not_found():
    client = APIClient()
    response = client.get("/api/questions/9999/")
    assert response.status_code == 404


@patch("executor.question_generator.generate_with_fallbacks")
@patch("executor.question_generator.model.encode")
@patch("sentence_transformers.util.cos_sim")
@pytest.mark.django_db
def test_generate_questions_success(mock_cos_sim, mock_encode, mock_generate):
    mock_generate.return_value = '''[
        {
            "title": "Sum of Two Numbers",
            "description": "Add two integers.",
            "sample_io": [{"input": "1 2", "output": "3"}],
            "explanation": "Add and return result",
            "constraints": "1 <= a, b <= 1000",
            "testcase_description": "Basic test",
            "topics": ["Math"],
            "companies_asked": ["Google"],
            "test_cases": [{"input": "10 20", "output": "30"}]
        }
    ]'''
    mock_encode.return_value = MagicMock()
    mock_cos_sim.return_value.max.return_value.item.return_value = 0.1

    client = APIClient()
    response = client.post("/api/generate_questions/", {
        "topic": "Math",
        "difficulty": "Easy"
    }, format="json")
    assert response.status_code == 201

def test_run_user_code_missing_fields():
    client = APIClient()
    payload = {"code": "print('Hello')"}  # Missing input and language
    response = client.post("/api/run_code/", payload, format='json')
    assert response.status_code == 400


@patch("executor.run_code.run_code")
def test_run_user_code_success(mock_run):
    mock_run.return_value = {
        "stdout": "Hello",
        "stderr": "",
        "error_line": None
    }
    client = APIClient()
    payload = {
        "code": "print('Hello')",
        "input": "",
        "language": "python"
    }
    response = client.post("/api/run_code/", payload, format='json')
    assert response.status_code == 200
    assert "stdout" in response.data


@patch("executor.code_grader.generate_grading_json")
def test_grade_code_success(mock_grader):
    mock_grader.return_value = json.dumps({
        "code_compiles": {"score": 2, "feedback": "The code compiles and runs without any errors."},
        "documentation": {"score": 2, "feedback": "Clear variable names."},
        "correctness": {"score": 2, "feedback": "Correct result."},
        "edge_cases": {"score": 1, "feedback": "Could cover more edge cases."},
        "efficiency": {"score": 1, "feedback": "Basic efficiency."},
        "final_score": 8,
        "comments": "Well done"
    })

    client = APIClient()
    payload = {
        "code": "print(2+2)",
        "question": "Add two numbers",
        "results": [
            {"input": "2 2", "expected_output": "4", "output": "4", "is_hidden": False}
        ]
    }
    response = client.post("/api/grade_code/", payload, format='json')
    print("Grade Code Response:", response.data)
    assert response.status_code == 200
    assert "final_score" in response.data
    assert response.data["final_score"] == 8
