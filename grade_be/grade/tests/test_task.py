import pytest
import os
from unittest.mock import patch, MagicMock
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from authentication.models import User
from grade.models import AnswerUpload
from grade.task import process_ocr_task

@pytest.fixture
def user(db):
    """Fixture for a standard student User."""
    return User.objects.create_user(username="ocr_student", email="ocr@example.com", password="password")

@pytest.fixture
def answer_upload(db, user):
    """Fixture for an AnswerUpload instance ready for OCR."""
    # Create a dummy file and save it to the media directory to simulate a real upload
    file_name = "ocr_test.pdf"
    file_path = os.path.join(settings.MEDIA_ROOT, file_name)
    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(b"dummy pdf content")

    return AnswerUpload.objects.create(
        file=file_name,
        user_id=user.id,
        roll_number="test_roll_123",
        question_paper_type="sample",
        question_paper_id=10,
    )

@patch('grade.task.process_answer_ocr')
def test_process_ocr_task_success(mock_process_ocr, answer_upload):
    """
    Tests the OCR task for a successful processing scenario.
    """
    # Mock the return value of the actual OCR function
    mock_process_ocr.return_value = {
        "success": True,
        "json_path": "/path/to/result.json",
        "images_dir": "/path/to/images",
        "roll_number": "R12345",
    }

    # Execute the task
    result = process_ocr_task(answer_upload.id)

    # Refresh the model instance from the database
    answer_upload.refresh_from_db()

    # Assertions
    assert result['success'] is True
    assert result['answer_upload_id'] == answer_upload.id
    assert answer_upload.ocr_processed is True
    assert answer_upload.ocr_json_path == "/path/to/result.json"
    assert answer_upload.ocr_images_dir == "/path/to/images"
    # assert answer_upload.roll_number == "R12345" # Omitted as per user instruction
    assert answer_upload.ocr_error is None
    mock_process_ocr.assert_called_once()

@patch('grade.task.process_answer_ocr')
def test_process_ocr_task_failure(mock_process_ocr, answer_upload):
    """
    Tests the OCR task for a failure scenario reported by the OCR processor.
    """
    # Mock a failure response from the OCR function
    mock_process_ocr.return_value = {
        "success": False,
        "error": "Could not detect text.",
    }

    # Execute the task
    result = process_ocr_task(answer_upload.id)
    answer_upload.refresh_from_db()

    # Assertions
    assert result['success'] is False
    assert answer_upload.ocr_processed is False
    assert answer_upload.ocr_error == "Could not detect text."
    assert answer_upload.ocr_json_path is None

@patch('grade.task.process_answer_ocr')
def test_process_ocr_task_exception(mock_process_ocr, answer_upload):
    """
    Tests the OCR task's exception handling.
    """
    # Mock the OCR function to raise an exception
    error_message = "A critical error occurred"
    mock_process_ocr.side_effect = Exception(error_message)

    # Execute the task
    result = process_ocr_task(answer_upload.id)
    answer_upload.refresh_from_db()

    # Assertions
    assert result['success'] is False
    assert result['error'] == error_message
    assert answer_upload.ocr_processed is False
    assert answer_upload.ocr_error == error_message 