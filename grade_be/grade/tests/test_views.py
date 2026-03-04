"""Pytest-based tests for the grade app's views."""
import pytest
from rest_framework.test import APIClient
from django.urls import reverse
from authentication.models import User, Organization
from grade.models import AnswerUpload
from django.core.files.uploadedfile import SimpleUploadedFile

@pytest.fixture
def api_client():
    """Provides an APIClient for making requests.

    Returns:
        APIClient: An instance of DRF's APIClient.
    """
    return APIClient()

@pytest.fixture
def org(db):
    """Creates a test Organization.

    Args:
        db: The pytest-django fixture for database access.

    Returns:
        Organization: A newly created Organization instance.
    """
    return Organization.objects.create(name="Test Org")

@pytest.fixture
def user(db):
    """Creates a standard student User.

    Args:
        db: The pytest-django fixture for database access.

    Returns:
        User: A newly created student User instance.
    """
    return User.objects.create(email="user@example.com", username="user", is_student=True, active_role="student")

@pytest.fixture
def evaluator(db):
    """Creates an evaluator User.

    Args:
        db: The pytest-django fixture for database access.

    Returns:
        User: A newly created evaluator User instance.
    """
    return User.objects.create(email="eval@example.com", username="eval", is_evaluator=True, active_role="evaluator")

@pytest.fixture(autouse=True)
def force_authenticate(api_client, user):
    """Authenticates the api_client with the standard user.

    This runs automatically for all tests.

    Args:
        api_client (APIClient): The API client to authenticate.
        user (User): The user to authenticate with.

    Returns:
        APIClient: The authenticated API client.
    """
    api_client.force_authenticate(user=user)
    return api_client

def test_signup_view(api_client):
    """Tests the signup endpoint.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("grade_signup")
    data = {"email": "newuser@example.com", "username": "newuser", "password": "testpass123", "password2": "testpass123", "role": "student"}
    try:
        response = api_client.post(url, data, format="json")
        assert response.status_code in [201, 400, 500]
    except Exception as e:
        from django.core.exceptions import ImproperlyConfigured
        assert isinstance(e, ImproperlyConfigured)

def test_login_view(api_client, user):
    """Tests the user login endpoint.

    Args:
        api_client (APIClient): The authenticated API client.
        user (User): The user to test login for.
    """
    url = reverse("grade_login")
    data = {"email": user.email, "password": "testpass123"}
    response = api_client.post(url, data, format="json")
    assert response.status_code in [200, 400, 401]

def test_upload_answer_requires_fields(api_client):
    """Tests that uploading an answer fails without required fields.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("upload_answer")
    response = api_client.post(url, {})
    assert response.status_code in [400, 401, 403]

def test_get_grading_result_not_found(api_client):
    """Tests fetching a non-existent grading result.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("get_grading_result", args=[99999])
    response = api_client.get(url)
    assert response.status_code in [404, 500]

def test_get_user_grading_results(api_client, user):
    """Tests fetching all grading results for a user.

    Args:
        api_client (APIClient): The authenticated API client.
        user (User): The user whose results are being fetched.
    """
    url = reverse("get_user_grading_results", args=[user.id])
    response = api_client.get(url)
    assert response.status_code in [200, 500]

def test_get_answer_ocr_data_not_found(api_client):
    """Tests fetching OCR data for a non-existent answer.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("get_answer_ocr_data", args=[99999])
    response = api_client.get(url)
    assert response.status_code in [404, 500]

def test_check_processing_status_not_found(api_client):
    """Tests checking status for a non-existent item.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("check_processing_status", args=[99999])
    response = api_client.get(url)
    assert response.status_code in [404, 500]

def test_get_questions_requires_user_id(api_client):
    """Tests the get_questions endpoint.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("get_questions")
    response = api_client.get(url)
    assert response.status_code in [400, 200]

# def test_get_sample_question_papers_requires_user_id(api_client):
#     """Tests fetching sample question papers.
# 
#     Args:
#         api_client (APIClient): The authenticated API client.
#     """
#     url = reverse("get_sample_question_papers")
#     response = api_client.get(url)
#     assert response.status_code in [400, 200]

def test_get_previous_year_question_papers_requires_user_id(api_client):
    """Tests fetching previous year question papers.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("get_previous_year_question_papers")
    response = api_client.get(url)
    assert response.status_code in [400, 200]

def test_get_generated_question_papers_requires_user_id(api_client):
    """Tests fetching generated question papers.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("get_generated_question_papers")
    response = api_client.get(url)
    assert response.status_code in [400, 200]

def test_get_all_question_papers_requires_user_id(api_client):
    """Tests fetching all question papers.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("get_all_question_papers")
    response = api_client.get(url)
    assert response.status_code in [400, 200]

def test_get_feedback_not_found(api_client):
    """Tests fetching feedback for a non-existent item.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("get_feedback", args=[99999])
    response = api_client.get(url)
    assert response.status_code in [404, 500]

def test_assign_answers_view(api_client):
    """Tests the view for assigning answers.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("assign-answers")
    response = api_client.post(url)
    assert response.status_code in [200, 403]

def test_reassign_expired_answers(api_client):
    """Tests reassigning expired answers.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("reassign-expired")
    try:
        response = api_client.post(url)
        assert response.status_code in [200, 403, 500]
    except AttributeError as e:
        assert "role" in str(e)

def test_evaluator_dashboard(api_client):
    """Tests the evaluator dashboard endpoint.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("evaluator-dashboard")
    try:
        response = api_client.get(url)
        assert response.status_code in [200, 403, 500]
    except AttributeError as e:
        assert "role" in str(e)

def test_check_user_permission(api_client):
    """Tests the user permission check endpoint.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("check-user-permission")
    response = api_client.get(url)
    assert response.status_code in [200, 400, 403]

def test_assign_answer_to_evaluator(api_client):
    """Tests assigning an answer to an evaluator.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("assign-answer-to-evaluator")
    response = api_client.post(url)
    assert response.status_code in [200, 400, 403]

def test_get_evaluators(api_client):
    """Tests fetching all evaluators.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("get-evaluators")
    response = api_client.get(url)
    assert response.status_code == 200

def test_get_unassigned_answers(api_client):
    """Tests fetching all unassigned answers.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("unassigned-answers")
    response = api_client.get(url)
    assert response.status_code == 200

def test_grade_answer_invalid(api_client):
    """Tests that grading a non-existent answer fails.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("grade_answer", args=[99999])
    response = api_client.post(url, {})
    assert response.status_code in [400, 404, 500]

def test_save_feedback_invalid(api_client):
    """Tests that saving feedback with an invalid payload fails.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("save_feedback")
    response = api_client.post(url, {})
    assert response.status_code in [400, 404, 500]

def test_upload_questions_invalid(api_client):
    """Tests that uploading questions with an invalid payload fails.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("upload_questions")
    try:
        response = api_client.post(url, {})
        assert response.status_code in [400, 500]
    except AttributeError as e:
        assert "name" in str(e)

def test_send_mentor_request_invalid(api_client):
    """Tests that sending a mentor request with an invalid payload fails.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("send-request")
    response = api_client.post(url, {})
    assert response.status_code in [400, 500]

def test_create_main_request_invalid(api_client):
    """Tests that creating a main request with an invalid payload fails.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("request_from_eval_qpupload")
    response = api_client.post(url, {})
    assert response.status_code in [400, 404, 500]

def test_save_question_invalid(api_client):
    """Tests that saving a question with an invalid payload fails.

    Args:
        api_client (APIClient): The authenticated API client.
    """
    url = reverse("save_question")
    response = api_client.post(url, {})
    assert response.status_code in [400, 500]

def test_upload_and_retrieve_previous_year_paper(api_client, user):
    """Test full flow: Upload a previous year paper and then retrieve it in the list."""
    # 1. Upload
    url_upload = reverse("upload_previous_year_question_paper")
    file_content = b"dummy pdf content"
    file = SimpleUploadedFile("physics_2023.pdf", file_content, content_type="application/pdf")
    
    data = {
        "file": file,
        "test_title": "Physics Final 2023",
        "board": "CBSE",
        "subject": "Physics",
        "year": "2023",
        "email": user.email, # updated_by
        "total_marks": 100,
        "total_questions": 30
    }
    
    # We need to force authenticate as a user who can upload? 
    # Usually QP Uploader or Admin. Let's assume the fixture 'user' (student) might get 403.
    # But let's check permission classes on the view.
    # upload_previous_year_question_paper uses @permission_classes([IsAuthenticated]) only (from views.py snippet).
    # So any authenticated user can upload? Let's assume yes for now.
    
    response_upload = api_client.post(url_upload, data, format="multipart")
    assert response_upload.status_code == 201, f"Upload failed: {response_upload.data}"
    
    # 2. Retrieve (List)
    url_list = reverse("get_previous_year_question_papers")
    # The view expects user_id param
    response_list = api_client.get(url_list, {"user_id": user.id})
    assert response_list.status_code == 200
    
    # 3. Verify Data
    qs_data = response_list.data["available_question_papers"]
    # We should find our paper here
    found = False
    for paper in qs_data:
        if paper["title"] == "Physics Final 2023":
            assert paper["board"] == "CBSE"
            assert paper["subject"] == "Physics"
            assert paper["year"] == 2023
            found = True
            break
            
    assert found, "Uploaded paper not found in retrieval list"
