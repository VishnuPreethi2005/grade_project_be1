import pytest
from rest_framework.test import APIClient

@pytest.mark.django_db
def test_run_code_python_success():
    client = APIClient()
    payload = {
        "code": "n = int(input())\narr = list(map(int, input().split()))\nprint(sum(arr))",
        "language": "python",
        "testcases": [
            {
                "input": "5\n1 2 3 4 5",
                "expected_output": "15"
            },
            {
                "input": "3\n-1 0 1",
                "expected_output": "0"
            },
            {
                "input": "1\n10",
                "expected_output": "10"
            }
        ]
    }
    response = client.post("/api/run_code/", payload, format="json")
    assert response.status_code == 200
    assert "results" in response.data
    assert response.data["score"] == 10.0
    assert all(r["passed"] for r in response.data["results"])


@pytest.mark.django_db
def test_run_code_missing_code_field():
    client = APIClient()
    payload = {
        "language": "python",
        "testcases": [
            {
                "input": "1\n2",
                "expected_output": "2"
            }
        ]
    }
    response = client.post("/api/run_code/", payload, format="json")
    assert response.status_code == 400
    assert response.data["error"] == "Code and language are required."


@pytest.mark.django_db
def test_run_code_missing_language_field():
    client = APIClient()
    payload = {
        "code": "print(2)",
        "testcases": [
            {
                "input": "",
                "expected_output": "2"
            }
        ]
    }
    response = client.post("/api/run_code/", payload, format="json")
    assert response.status_code == 400
    assert response.data["error"] == "Code and language are required."


@pytest.mark.django_db
def test_run_code_unsupported_language():
    client = APIClient()
    payload = {
        "code": "print('Hi')",
        "language": "ruby",
        "testcases": [
            {
                "input": "",
                "expected_output": "Hi"
            }
        ]
    }
    response = client.post("/api/run_code/", payload, format="json")
    assert response.status_code == 400
    assert "Unsupported language" in response.data["error"]


@pytest.mark.django_db
def test_run_code_runtime_error():
    client = APIClient()
    payload = {
        "code": "print(1/0)",
        "language": "python",
        "testcases": [
            {
                "input": "",
                "expected_output": "inf"
            }
        ]
    }
    response = client.post("/api/run_code/", payload, format="json")
    assert response.status_code == 400
    assert "Traceback" in response.data["stderr"]
    assert isinstance(response.data.get("error_line"), int)

