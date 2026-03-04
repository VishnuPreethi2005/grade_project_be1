import pytest
from rest_framework.test import APIClient
from unittest.mock import patch
import json

@pytest.mark.django_db
@patch("executor.views.generate_grading_json")
def test_grade_code_success(mock_generate):
    mock_generate.return_value = json.dumps({
        "code_compiles": {"score": 2, "feedback": "Fine"},
        "documentation": {"score": 2, "feedback": "Ok"},
        "correctness": {"score": 2, "feedback": "Correct"},
        "edge_cases": {"score": 1},
        "efficiency": {"score": 1},
        "final_score": 8,
        "comments": "Good"
    })

    client = APIClient()
    payload = {
        "code": "print(1+1)",
        "question": "Add numbers",
        "results": [
            {"input": "1 1", "expected_output": "2", "output": "2", "is_hidden": False}
        ]
    }

    res = client.post("/api/grade_code/", payload, format="json")
    assert res.status_code == 200
    assert res.data["final_score"] == 8
    assert res.data["correctness"]["feedback"] == "Correct"


@pytest.mark.django_db
def test_grade_code_missing_code_field():
    client = APIClient()
    payload = {
        "question": "Test",
        "results": [{"input": "1", "expected_output": "1", "output": "1", "is_hidden": False}]
    }
    res = client.post("/api/grade_code/", payload, format="json")
    assert res.status_code == 400
    assert "Missing" in res.data["error"]


@pytest.mark.django_db
def test_grade_code_missing_results():
    client = APIClient()
    payload = {
        "code": "print(1)",
        "question": "Test"
    }
    res = client.post("/api/grade_code/", payload, format="json")
    assert res.status_code == 400
    assert "No test cases provided" in res.data["error"]


@pytest.mark.django_db
def test_grade_code_invalid_results_format():
    client = APIClient()
    payload = {
        "code": "print(1)",
        "question": "Test",
        "results": "not_a_list"
    }
    res = client.post("/api/grade_code/", payload, format="json")
    assert res.status_code == 400
    assert "must be a list" in res.data["error"].lower()
