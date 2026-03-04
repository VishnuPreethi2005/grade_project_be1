import pytest
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient
import subprocess

pytestmark = pytest.mark.django_db

client = APIClient()

@patch("executor.run_code.subprocess.run")
def test_run_python_code_success(mock_subprocess):
    mock_result = MagicMock()
    mock_result.stdout = "5\n"
    mock_result.returncode = 0
    mock_subprocess.return_value = mock_result

    payload = {
        "code": "a = int(input())\nb = int(input())\nprint(a + b)",
        "language": "python",
        "testcases": [{"input": "2\n3", "expected_output": "5"}]
    }

    response = client.post("/api/run_code/", payload, format="json")
    assert response.status_code == 200
    data = response.data

    assert "results" in data
    assert data["score"] == 10
    assert data["results"][0]["passed"] is True


@patch("executor.run_code.subprocess.run")
def test_run_python_code_syntax_error(mock_subprocess):
    mock_subprocess.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["python"],
        output="",
        stderr="File \"<string>\", line 1\n    a = int(input()\n                      ^\nSyntaxError: unexpected EOF while parsing\n"
    )

    payload = {
        "code": "a = int(input()",  # Invalid code
        "language": "python",
        "testcases": [{"input": "2", "expected_output": "2"}]
    }

    response = client.post("/api/run_code/", payload, format="json")
    assert response.status_code == 200
    data = response.data

    assert "results" in data
    assert data["results"][0]["passed"] is False
    assert "Syntax Error" in data["results"][0]["error"]


def test_run_code_missing_fields():
    payload = {"language": "python"}  # Missing 'code'
    response = client.post("/api/run_code/", payload, format="json")
    assert response.status_code == 400
    assert response.data["error"] == "Code and language are required."


def test_run_code_unsupported_language():
    payload = {
        "code": "print(42)",
        "language": "javascript"  # Not supported
    }
    response = client.post("/api/run_code/", payload, format="json")
    assert response.status_code == 400
    assert response.data["error"] == "Unsupported language"
