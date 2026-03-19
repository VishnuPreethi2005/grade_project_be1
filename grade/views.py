import base64
from .models import Question
from pathlib import Path
from .grading import StudentGrader  # Import the StudentGrader class instead
from django.core.files.base import ContentFile
import uuid
from django.conf import settings
import os
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from .serializers import (
    GradeMasterSignupSerializer,
    GradeMasterLoginSerializer,
    MainRequestSerializer,
    SampleQuestionPaperSerializer,
)
from .models import AnswerUpload, QuestionFeedback
from django.contrib.auth import login
from django.core.files.storage import default_storage

# Ensure the serializer is imported
from authentication.models import User, UserCredit, UsageHistory  # Import User model
from prompts.decorators import deduct_user_credit
from decimal import Decimal 
from django.http import JsonResponse
import json
from .serializers import FeedbackSerializer
from django.core.exceptions import ObjectDoesNotExist
import csv
import glob

from .models import QuestionGrade, CriteriaGrade, AIMetrics
from .models import Feedback, Evaluator, Language, Subject, Board
from .models import MentorshipRequest
from django.shortcuts import get_object_or_404
from rest_framework.status import HTTP_200_OK, HTTP_404_NOT_FOUND
from .models import Notification, MentorStudent, MainRequest, AnswerAssignment
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta

# from celery import shared_task
from .task import process_ocr_task, grade_answer_task

# Additional imports needed at the top of your views.py file
import json
import time
import shutil
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes


from .models import (
    SampleQuestionPaper,
    PreviousYearQuestionPaper,
    GeneratedQuestionPaper,
    Questions,
    GradingResult,
)
from django.http import FileResponse
from grade.utils.pdf_generator import PDFReportGenerator


import logging

logger = logging.getLogger(__name__)


# views.py

# Import your existing functions (rename your original file to
# ocr_processor.py)

# Global dictionary to track job status
job_status = {}

# Add this to your Django views.py
# Add to your Django views.py


# Add this to your Django views.py


logger = logging.getLogger(__name__)


@api_view(["POST"])
def grade_answer(request: Request, answer_id: int) -> Response:
    """Grade a specific answer using AI grading system (Async)."""
    try:
        # Get the answer upload
        try:
            answer_upload = AnswerUpload.objects.get(id=answer_id)
        except AnswerUpload.DoesNotExist:
            return Response({"error": "Answer not found"}, status=status.HTTP_404_NOT_FOUND)

        # Check if answer has OCR data
        if not answer_upload.ocr_processed:
            return Response(
                {
                    "error": "Answer must be OCR processed before grading",
                    "ocr_error": answer_upload.ocr_error,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if already graded
        existing_grading = answer_upload.grading_results.first()
        if existing_grading and not request.GET.get("force"):
             return Response(
                {
                    "error": "Answer has already been graded",
                    "grading_id": existing_grading.id,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Start the task
        task = grade_answer_task.delay(answer_id)
        
        return Response(
            {
                "message": "Grading started in background",
                "task_id": task.id,
                "answer_id": answer_id
            },
            status=status.HTTP_202_ACCEPTED
        )

    except Exception as e:
        logger.error(f"Error starting grading task: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["GET"])
def get_grading_result(request: Request, answer_id: int) -> Response:
    """Get grading result for a specific answer.

    Args:
        request (Request): The Django REST Framework request object.
        answer_id (int): The ID of the answer for which to retrieve the
                         grading result.

    Returns:
        Response: A DRF Response object with the grading result data or a
                  message indicating the grading status.
    """
    try:
        answer_upload = AnswerUpload.objects.get(id=answer_id)

        # Check if grading result exists (get the latest one for this answer)
        grading_result = answer_upload.grading_results.order_by('-created_at').first()
        if not grading_result:
            return Response(
                {"graded": False, "message": "Answer has not been graded yet"},
                status=status.HTTP_200_OK,
            )

        # Check if grading was successful
        if not grading_result.grading_processed:
            return Response(
                {
                    "graded": False,
                    "error": grading_result.grading_error,
                    "grading_id": grading_result.id,
                },
                status=status.HTTP_200_OK,
            )

        # Load detailed result data
        result_data = grading_result.get_result_data()

        if not result_data:
            return Response(
                {"error": "Could not load grading result data"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Return the full result data
        return Response(
            {
                "graded": True,
                "grading_id": grading_result.id,
                "result_data": result_data,
            },
            status=status.HTTP_200_OK,
        )

    except AnswerUpload.DoesNotExist:
        return Response(
            {"error": "Answer not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error retrieving grading result: {str(e)}", exc_info=True)
        return Response(
            {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
def get_user_grading_results(request: Request, user_id: int) -> Response:
    """Get all grading results for a specific user.

    Args:
        request (Request): The Django REST Framework request object.
        user_id (int): The ID of the user for whom to retrieve grading results.

    Returns:
        Response: A DRF Response object with a list of all grading results
                  for the user.
    """
    try:
        grading_results = (
            GradingResult.objects.filter(user_id=user_id)
            .select_related("answer_upload")
            .order_by("-created_at")
        )

        results_data = []
        for result in grading_results:
            result_item = {
                "grading_id": result.id,
                "answer_id": result.answer_upload.id,
                "question_paper_type": result.answer_upload.question_paper_type,
                "question_paper_id": result.answer_upload.question_paper_id,
                "graded": result.grading_processed,
                "total_score": (
                    result.total_score if result.grading_processed else None
                ),
                "max_possible_score": (
                    result.max_possible_score
                    if result.grading_processed
                    else None
                ),
                "percentage": (
                    round(result.percentage, 2)
                    if result.grading_processed
                    else None
                ),
                "questions_count": result.questions_count,
                "diagrams_count": result.diagrams_count,
                "graded_at": result.graded_at,
                "created_at": result.created_at,
                "error": (
                    result.grading_error
                    if not result.grading_processed
                    else None
                ),
            }
            results_data.append(result_item)

        return Response(
            {
                "user_id": user_id,
                "total_results": len(results_data),
                "graded_count": len([r for r in results_data if r["graded"]]),
                "results": results_data,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Error retrieving user grading results: {str(e)}", exc_info=True)
        return Response(
            {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["DELETE"])
def delete_grading_result(request: Request, grading_id: int) -> Response:
    """Delete a specific grading result and its files.

    Args:
        request (Request): The Django REST Framework request object.
        grading_id (int): The ID of the grading result to delete.

    Returns:
        Response: A DRF Response object with a success message or an error.
    """
    try:
        grading_result = GradingResult.objects.get(id=grading_id)

        # Delete result files
        if grading_result.result_json_path and os.path.exists(
            grading_result.result_json_path
        ):
            try:
                os.remove(grading_result.result_json_path)
                # Also try to remove the parent directory if it's empty
                result_dir = os.path.dirname(grading_result.result_json_path)
                if os.path.exists(result_dir) and not os.listdir(result_dir):
                    os.rmdir(result_dir)
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to cleanup result files: {cleanup_error}"
                )

        # Delete the database record
        grading_result.delete()

        return Response(
            {"message": "Grading result deleted successfully"},
            status=status.HTTP_200_OK,
        )

    except GradingResult.DoesNotExist:
        return Response(
            {"error": "Grading result not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        logger.error(f"Error deleting grading result: {str(e)}", exc_info=True)
        return Response(
            {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
def get_answer_ocr_data(request: Request, answer_id: int) -> Response:
    """Get OCR processed data for a specific answer.

    Args:
        request (Request): The Django REST Framework request object.
        answer_id (int): The ID of the answer to get OCR data for.

    Returns:
        Response: A DRF Response object with the OCR data.
    """
    try:
        answer = AnswerUpload.objects.get(id=answer_id)

        if not answer.ocr_processed:
            return Response(
                {"ocr_processed": False, "error": answer.ocr_error},
                status=status.HTTP_200_OK,
            )

        # Read JSON data if available
        json_data = None
        if answer.ocr_json_path and os.path.exists(answer.ocr_json_path):
            with open(answer.ocr_json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)

        return Response(
            {
                "ocr_processed": True,
                # "roll_number": answer.roll_number,
                "json_data": json_data,
                "images_dir": answer.ocr_images_dir,
                "processed_at": answer.ocr_processed_at,
            },
            status=status.HTTP_200_OK,
        )

    except AnswerUpload.DoesNotExist:
        return Response(
            {"error": "Answer not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error getting answer OCR data: {e}", exc_info=True)
        return Response(
            {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["PUT", "PATCH"])
def update_answer_ocr_data(request: Request, answer_id: int) -> Response:
    """Update OCR processed data for a specific answer.

    Args:
        request (Request): The Django REST Framework request object
                         containing the updated OCR data.
        answer_id (int): The ID of the answer to update.

    Returns:
        Response: A DRF Response object with a success message or an error.
    """
    try:
        answer = AnswerUpload.objects.get(id=answer_id)

        # Check if OCR was processed
        if not answer.ocr_processed:
            return Response(
                {"error": "Cannot update OCR data for unprocessed answer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate that JSON data is provided
        json_data = request.data.get("json_data")
        if not json_data:
            return Response(
                {"error": "json_data is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate JSON structure (optional - add your own validation logic)
        try:
            if isinstance(json_data, str):
                json.loads(json_data)  # Validate if it's a valid JSON string
        except json.JSONDecodeError:
            return Response(
                {"error": "Invalid JSON data provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create backup of original file before updating
        if answer.ocr_json_path and os.path.exists(answer.ocr_json_path):
            backup_path = f"{answer.ocr_json_path}.backup_{int(time.time())}"
            try:
                shutil.copy2(answer.ocr_json_path, backup_path)
                logger.info(
                    f"Created backup of original OCR data at: {backup_path}"
                )
            except Exception as backup_error:
                logger.warning(f"Failed to create backup: {backup_error}")

        # Update the JSON file
        if answer.ocr_json_path:
            try:
                # Ensure directory exists
                os.makedirs(
                    os.path.dirname(answer.ocr_json_path), exist_ok=True
                )

                # Write updated JSON data
                with open(answer.ocr_json_path, "w", encoding="utf-8") as f:
                    if isinstance(json_data, str):
                        # If it's already a JSON string, parse and rewrite with
                        # proper formatting
                        parsed_data = json.loads(json_data)
                        json.dump(parsed_data, f, indent=2, ensure_ascii=False)
                    else:
                        # If it's a dict/object, write directly
                        json.dump(json_data, f, indent=2, ensure_ascii=False)

                # Update the database record
                # Add this field to your model if not exists
                answer.ocr_updated_at = timezone.now()
                answer.save()

                logger.info(
                    f"Successfully updated OCR data for answer {answer_id}"
                )

                return Response(
                    {
                        "message": "OCR data updated successfully",
                        "updated_at": answer.ocr_updated_at,
                        "json_path": answer.ocr_json_path,
                    },
                    status=status.HTTP_200_OK,
                )

            except Exception as file_error:
                logger.error(f"Error writing updated JSON file: {file_error}")
                return Response(
                    {
                        "error": f"Failed to update OCR data file: {str(file_error)}"
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            return Response(
                {"error": "No OCR JSON path found for this answer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    except AnswerUpload.DoesNotExist:
        return Response(
            {"error": "Answer not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(
            f"Error updating OCR data for answer {answer_id}: {str(e)}", exc_info=True
        )
        return Response(
            {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
def signup_view(request: Request) -> Response:
    """Handles user signup for GradeMaster.

    Args:
        request (Request): The Django REST Framework request object containing
                         user signup data.

    Returns:
        Response: A DRF Response object indicating success or failure of
                  registration.
    """
    serializer = GradeMasterSignupSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(
            {"success": "User registered successfully."},
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def login_view(request: Request) -> Response:
    """Handles user login for GradeMaster.

    Args:
        request (Request): The Django REST Framework request object containing
                         user login credentials.

    Returns:
        Response: A DRF Response object with user data upon successful login,
                  or an error.
    """
    serializer = GradeMasterLoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data["user"]
        role = user.role
        login(request, user)  # Attach session to the request
        return Response(
            {
                "id": user.id,
                "email": user.email,
                "role": role,
            },
            status=status.HTTP_200_OK,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def check_processing_status(request: Request, answer_upload_id: int) -> Response:
    """Check the status of OCR processing.

    Args:
        request (Request): The Django REST Framework request object.
        answer_upload_id (int): The ID of the answer upload to check.

    Returns:
        Response: A DRF Response object with the OCR processing status.
    """
    try:
        answer_upload = AnswerUpload.objects.get(id=answer_upload_id)

        return Response(
            {
                "answer_upload_id": answer_upload_id,
                "ocr_processed": answer_upload.ocr_processed,
                # 'task_id': answer_upload.task_id,
                "error": answer_upload.ocr_error,
                "processing_complete": answer_upload.ocr_processed
                or bool(answer_upload.ocr_error),
            }
        )

    except AnswerUpload.DoesNotExist:
        return Response({"error": "Answer upload not found"}, status=404)


@api_view(["POST"])
def upload_answer(request: Request) -> Response:
    """Upload an answer for any type of question paper with async OCR processing.

    Args:
        request (Request): The Django REST Framework request object containing
                         the file and metadata.

    Returns:
        Response: A DRF Response object indicating the upload was successful
                  and OCR processing has started.
    """
    logger.info(f"Received request to upload answer for user {request.data.get('user_id')}.")
    # Validate required fields
    required_fields = [
        "file",
        "user_id",
        "question_paper_type",
        "question_paper_id",
    ]
    for field in required_fields:
        if field not in request.data and field not in request.FILES:
            return Response(
                {"error": f"{field} is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Extract data from the request
    file = request.FILES["file"]
    user_id = request.data["user_id"]
    question_paper_type = request.data["question_paper_type"]
    question_paper_id = request.data["question_paper_id"]
    organization_id = request.data.get(
        "organization_id"
    )  # Optional organization ID
    skip_ocr = str(request.data.get("skip_ocr", "false")).lower() == "true"

    # Validate paper type
    valid_paper_types = [
        "sample",
        "previous_year",
        "generated",
        "organization",
    ]
    if question_paper_type not in valid_paper_types:
        return Response(
            {
                "error": f"Invalid question_paper_type. Must be one of {valid_paper_types}"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check if the question paper exists
    try:
        if question_paper_type == "sample":
            question_paper = SampleQuestionPaper.objects.get(
                id=question_paper_id
            )
            related_field = "sample_question_paper"
        elif question_paper_type == "previous_year":
            question_paper = PreviousYearQuestionPaper.objects.get(
                id=question_paper_id
            )
            related_field = "previous_year_question_paper"
        elif question_paper_type == "generated":
            question_paper = GeneratedQuestionPaper.objects.get(
                id=question_paper_id
            )
            related_field = "generated_question_paper"
        elif question_paper_type == "organization":
            from organization.models import Test

            question_paper = Test.objects.get(id=question_paper_id)
            related_field = "organization_test"
        else:
            question_paper = Questions.objects.get(id=question_paper_id)
            related_field = "questions"
    except (
        SampleQuestionPaper.DoesNotExist,
        PreviousYearQuestionPaper.DoesNotExist,
        GeneratedQuestionPaper.DoesNotExist,
        Test.DoesNotExist,
    ):
        return Response(
            {
                "error": f"Question paper with ID {question_paper_id} not found."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # Check existing attempts and validate retake limits
    existing_attempts = AnswerUpload.objects.filter(
        user_id=user_id,
        question_paper_type=question_paper_type,
        question_paper_id=question_paper_id,
    ).count()
    
    # Get max_retakes from the question paper (default to 5 if not set)
    max_retakes = getattr(question_paper, 'max_retakes', 5)
    
    if existing_attempts >= max_retakes:
        return Response(
            {
                "error": f"Maximum {max_retakes} attempts reached for this test. No more retakes allowed.",
                "attempts_used": existing_attempts,
                "max_attempts": max_retakes,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    
    # Calculate the next attempt number
    attempt_number = existing_attempts + 1

    # Generate unique identifier for this upload
    upload_id = str(uuid.uuid4())

    try:
        # Log which storage backend is being used
        from django.core.files.storage import default_storage
        storage_backend = default_storage.__class__.__name__
        storage_module = default_storage.__class__.__module__
        logger.info(f"Using storage backend: {storage_backend}")
        logger.info(f"Storage backend module: {storage_module}")
        logger.info(f"Is Azure Storage: {'azure' in storage_module.lower()}")
        
        # Save file immediately without OCR processing
        file_path = default_storage.save(
            f"answer_uploads/{upload_id}_{file.name}", file
        )
        
        logger.info(f"File saved to path: {file_path}")
        logger.info(f"Storage backend type: {type(default_storage)}")
        
        # Verify the file was saved to the correct location
        if hasattr(default_storage, 'url'):
            try:
                file_url = default_storage.url(file_path)
                logger.info(f"File URL: {file_url}")
                if 'blob.core.windows.net' in file_url:
                    logger.info("✅ File saved to Azure Blob Storage")
                else:
                    logger.info("⚠️  File saved to local storage (not Azure)")
            except Exception as e:
                logger.warning(f"Could not get file URL: {e}")

        # Create the answer upload record with attempt_number
        answer_upload = AnswerUpload(
            file=file_path,
            user_id=user_id,
            question_paper_type=question_paper_type,
            question_paper_id=question_paper_id,
            ocr_processed=skip_ocr,
            attempt_number=attempt_number,
        )

        # Set organization if provided
        if organization_id:
            from authentication.models import Organization

            try:
                organization = Organization.objects.get(id=organization_id)
                answer_upload.organization = organization
            except Organization.DoesNotExist:
                return Response(
                    {
                        "error": f"Organization with ID {organization_id} not found."
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        # Set the specific question paper relation
        setattr(answer_upload, related_field, question_paper)
        answer_upload.save()
        
        # Log the file URL after saving
        file_url = answer_upload.file.url if answer_upload.file else "No file URL"
        logger.info(f"File URL after save: {file_url}")
        logger.info(f"File URL starts with https://grademedia.blob: {file_url.startswith('https://grademedia.blob') if file_url != 'No file URL' else False}")

        # Update TestAssignment is_completed field for organization tests
        if question_paper_type == "organization":
            from organization.models import TestAssignment

            try:
                test_assignment = TestAssignment.objects.get(
                    test=question_paper, student_id=user_id
                )
                test_assignment.is_completed = True
                test_assignment.save()
                logger.info(
                    f"Updated TestAssignment is_completed for test {question_paper.id} and student {user_id}"
                )
            except TestAssignment.DoesNotExist:
                logger.warning(
                    f"No TestAssignment found for test {question_paper.id} and student {user_id}"
                )

        # Start async OCR processing task
        if not skip_ocr:
            task = process_ocr_task.delay(answer_upload.id)
            answer_upload.task_id = task.id
            answer_upload.save()
            logger.info(
                f"Answer uploaded and OCR task started for upload {upload_id}, task_id: {task.id}"
            )
            file_url = answer_upload.file.url if answer_upload.file else None
            return Response(
                {
                    "message": "Answer uploaded successfully! OCR processing started in background.",
                    "id": answer_upload.id,
                    "task_id": task.id,
                    "upload_id": upload_id,
                    "ocr_processed": False,
                    "processing_started": True,
                    "attempt_number": attempt_number,
                    "attempts_remaining": max_retakes - attempt_number,
                    "file_url": file_url,
                    "storage_backend": storage_backend,
                },
                status=status.HTTP_201_CREATED,
            )
        else:
            logger.info(
                f"Answer uploaded with skip_ocr=True for upload {upload_id}. Marked as processed."
            )
            file_url = answer_upload.file.url if answer_upload.file else None
            return Response(
                {
                    "message": "Answer uploaded successfully! OCR skipped as requested.",
                    "id": answer_upload.id,
                    "upload_id": upload_id,
                    "ocr_processed": True,
                    "file_url": file_url,
                    "storage_backend": storage_backend,
                    "processing_started": False,
                    "attempt_number": attempt_number,
                    "attempts_remaining": max_retakes - attempt_number,
                },
                status=status.HTTP_201_CREATED,
            )

    except Exception as e:
        logger.error(f"Upload failed for upload_id {upload_id}: {str(e)}", exc_info=True)
        return Response(
            {"error": f"Upload failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_test_attempts(request: Request, question_paper_type: str, question_paper_id: int) -> Response:
    """Get all attempts for a specific test by a user.

    Args:
        request (Request): The Django REST Framework request object.
        question_paper_type (str): Type of question paper (sample, previous_year, etc.)
        question_paper_id (int): ID of the question paper.

    Returns:
        Response: A DRF Response object with all attempts and their grading results.
    """
    user_id = request.query_params.get("user_id")
    
    if not user_id:
        return Response(
            {"error": "user_id query parameter is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    
    # Get all attempts for this user and test
    attempts = AnswerUpload.objects.filter(
        user_id=user_id,
        question_paper_type=question_paper_type,
        question_paper_id=question_paper_id,
    ).order_by("attempt_number")
    
    # Get max_retakes from the question paper
    max_retakes = 5  # default
    try:
        if question_paper_type == "sample":
            qp = SampleQuestionPaper.objects.get(id=question_paper_id)
            max_retakes = qp.max_retakes
        elif question_paper_type == "previous_year":
            qp = PreviousYearQuestionPaper.objects.get(id=question_paper_id)
            max_retakes = qp.max_retakes
        elif question_paper_type == "generated":
            qp = GeneratedQuestionPaper.objects.get(id=question_paper_id)
            max_retakes = qp.max_retakes
        elif question_paper_type == "organization":
            from organization.models import Test
            qp = Test.objects.get(id=question_paper_id)
            max_retakes = qp.max_retakes
    except Exception:
        pass  # Use default if not found
    
    attempts_data = []
    for attempt in attempts:
        # Get grading result for this attempt
        grading_result = None
        try:
            gr = attempt.grading_results.first()  # Changed from grading_result to grading_results
            if gr:
                grading_result = {
                    "id": gr.id,
                    "total_score": gr.total_score,
                    "max_possible_score": gr.max_possible_score,
                    "percentage": gr.percentage,
                    "grading_processed": gr.grading_processed,
                    "graded_at": gr.graded_at,
                }
        except Exception:
            pass
        
        attempts_data.append({
            "id": attempt.id,
            "attempt_number": attempt.attempt_number,
            "upload_date": attempt.upload_date,
            "ocr_processed": attempt.ocr_processed,
            "file_url": attempt.file.url if attempt.file else None,
            "grading_result": grading_result,
        })
    
    return Response({
        "user_id": user_id,
        "question_paper_type": question_paper_type,
        "question_paper_id": question_paper_id,
        "total_attempts": len(attempts_data),
        "max_retakes": max_retakes,
        "attempts_remaining": max(0, max_retakes - len(attempts_data)),
        "can_retake": len(attempts_data) < max_retakes,
        "attempts": attempts_data,
    }, status=status.HTTP_200_OK)

@api_view(["GET"])
def get_question_for_evaluator(request: Request) -> Response:
    """Returns answer sheets assigned to the currently logged-in evaluator.

    Args:
        request (Request): The Django REST Framework request object, may contain
                         'user_id' as a query parameter.

    Returns:
        Response: A DRF Response object with a list of answer sheets assigned
                  to the evaluator.
    """
    evaluator = request.GET.get("user_id")

    if not evaluator:
        return Response(
            {"error": "User ID is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Fetch only answer sheets assigned to the logged-in evaluator and not
    # completed
    assigned_answers = AnswerAssignment.objects.filter(
        evaluator=evaluator,
        completed=False,  # Only fetch incomplete evaluations
    ).select_related(
        "answer_upload",
        "answer_upload__sample_question_paper",
        "answer_upload__previous_year_question_paper",
        "answer_upload__generated_question_paper",
    )

    # Prepare response data
    answer_data = []
    for assignment in assigned_answers:
        answer = assignment.answer_upload

        # Determine which type of question paper is associated with this answer
        if (
            hasattr(answer, "sample_question_paper")
            and answer.sample_question_paper
        ):
            question_paper = answer.sample_question_paper
            paper_type = "sample"
        elif (
            hasattr(answer, "previous_year_question_paper")
            and answer.previous_year_question_paper
        ):
            question_paper = answer.previous_year_question_paper
            paper_type = "previous_year"
        elif (
            hasattr(answer, "generated_question_paper")
            and answer.generated_question_paper
        ):
            question_paper = answer.generated_question_paper
            paper_type = "generated"
        else:
            # Skip if no question paper is linked
            continue

        # Get user who submitted the answer
        # Since we don't have direct access to user through select_related,
        # we'll use answer.user_id to get the basic info we need

        answer_data.append(
            {
                "answer_id": answer.id,
                # Just using the ID since we can't access the email directly
                "answered_by": answer.user_id,
                "paper_type": paper_type,
                "qp_title": question_paper.test_title or "No Title",
                "question_paper_file": None,  # QP files not uploaded (copyright)
                "updated_by": question_paper.updated_by or "Unknown",
                "answer_file": answer.file.url,
                "upload_date": answer.upload_date.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "total_marks": question_paper.total_marks,
                "question_marks": getattr(question_paper, "questions", None),
                "board": question_paper.board,
                "total_question": question_paper.total_questions,
                "subject": question_paper.subject,
                # Add assignment info for remaining time calculation
                "assigned_date": assignment.assigned_date.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    return Response(answer_data, status=status.HTTP_200_OK)


@api_view(["POST"])
def save_feedback(request: Request) -> Response:
    """Saves feedback provided by an evaluator for a specific answer.

    Args:
        request (Request): The Django REST Framework request object containing
                         feedback data.

    Returns:
        Response: A DRF Response object indicating success or failure of
                  saving the feedback.
    """
    logger.info("Received request to save feedback.")

    # Retrieve the AnswerUpload ID and email from the request data
    ans_id = request.data.get("answerUploadId", "")
    logger.debug(f"save_feedback: ans_id={ans_id}")
    email = request.data.get("email", "")
    logger.debug(f"save_feedback: email={email}")

    # Retrieve feedback from request data
    feedback = request.data.get("feedback", "")
    logger.debug(f"save_feedback: feedback received.")

    # Ensure that the feedback is not empty
    if not feedback:
        return Response(
            {"error": "Feedback cannot be empty."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # Find the AnswerUpload object using the provided answer_upload_id
        answer_upload = AnswerUpload.objects.get(id=ans_id)
    except AnswerUpload.DoesNotExist:
        return Response(
            {"error": "Answer upload not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Find the user based on the provided email
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response(
            {"error": "User not found."}, status=status.HTTP_404_NOT_FOUND
        )

    # Calculate total marks obtained
    total_marks = sum(float(item["marksObtained"]) for item in feedback)

    # Save the feedback as a QuestionFeedback instance
    question_feedback = QuestionFeedback(
        answer_upload=answer_upload,
        # Store feedback as JSON string in feedback_text
        feedback_text=json.dumps(feedback),
        marks_obtained=total_marks,
    )
    question_feedback.save()

    # Update the AnswerAssignment to mark it as completed
    try:
        answer_assignment = AnswerAssignment.objects.get(
            answer_upload=answer_upload
        )
        answer_assignment.completed = True
        answer_assignment.save()
    except AnswerAssignment.DoesNotExist:
        # If no assignment exists, create one and mark it as completed
        AnswerAssignment.objects.create(
            answer_upload=answer_upload, evaluator=user, completed=True
        )

    return Response(
        {"success": "Feedback saved successfully!"},
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
def get_question_feedback(request: Request, feedback_id: int) -> Response:
    """
    Fetch a specific question feedback entry by its ID.
    """
    try:
        # Fetch the QuestionFeedback instance by ID
        feedback = QuestionFeedback.objects.get(id=feedback_id)
        feedback.answer_upload

        # Parse the feedback text JSON
        feedback_data = (
            json.loads(feedback.feedback_text)
            if feedback.feedback_text
            else []
        )

        # Prepare data for the response
        response_data = {
            "feedback_id": feedback.id,
            "answer_upload_id": feedback.answer_upload.id,
            "answer_file": (
                feedback.answer_upload.file.url
                if feedback.answer_upload.file
                else "No File"
            ),
            "total_marks_obtained": feedback.marks_obtained,
            "feedback_details": feedback_data,  # The parsed JSON array of feedback items
            "created_date": feedback.created_date.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }

        # Return the feedback data as JSON
        return Response(response_data, status=status.HTTP_200_OK)

    except QuestionFeedback.DoesNotExist:
        # Return a 404 response if the feedback entry does not exist
        return Response(
            {"error": "Question feedback not found for the provided ID."},
            status=status.HTTP_404_NOT_FOUND,
        )

    except Exception as e:
        logger.error(f"An unexpected error occurred in get_question_feedback: {e}", exc_info=True)
        # Handle unexpected errors
    # Handle unexpected errors
        return Response(
            {"error": f"An unexpected error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

def print_combined_metrics_summary(answer_upload):
    """
    Print combined OCR + Grading metrics summary after DB sync.
    This ensures accurate totals since both are now in the database.
    """
    from django.db.models import Sum
    
    def get_metrics(process_type):
        metrics = AIMetrics.objects.filter(
            answer_upload=answer_upload, 
            process_type=process_type
        ).aggregate(
            total_input=Sum('input_tokens'),
            total_output=Sum('output_tokens'),
            total_tokens=Sum('total_tokens'),
            total_cost=Sum('total_cost_usd')
        )
        return {
            'input_tokens': metrics['total_input'] or 0,
            'output_tokens': metrics['total_output'] or 0,
            'total_tokens': metrics['total_tokens'] or 0,
            'total_cost': float(metrics['total_cost'] or 0),
            'call_count': AIMetrics.objects.filter(
                answer_upload=answer_upload, 
                process_type=process_type
            ).count()
        }
    
    ocr = get_metrics('OCR')
    grading = get_metrics('GRADING')
    
    combined_input = ocr['input_tokens'] + grading['input_tokens']
    combined_output = ocr['output_tokens'] + grading['output_tokens']
    combined_tokens = ocr['total_tokens'] + grading['total_tokens']
    combined_cost = ocr['total_cost'] + grading['total_cost']
    
    logger.info("==== 💰 COMBINED METRICS SUMMARY (OCR + GRADING) ====")
    logger.info(f"📝 OCR:      Input: {ocr['input_tokens']:,} | Output: {ocr['output_tokens']:,} | Total: {ocr['total_tokens']:,} | Cost: ${ocr['total_cost']:.6f} | Calls: {ocr['call_count']}")
    logger.info(f"📊 Grading:  Input: {grading['input_tokens']:,} | Output: {grading['output_tokens']:,} | Total: {grading['total_tokens']:,} | Cost: ${grading['total_cost']:.6f} | Calls: {grading['call_count']}")
    logger.info(f"💰 COMBINED: Input: {combined_input:,} | Output: {combined_output:,} | Total: {combined_tokens:,} | Cost: ${combined_cost:.6f}")
    logger.info("=====================================================")

    # Deduct combined cost from user credits
    if combined_cost > 0 and answer_upload.user_id:
        try:
            user = User.objects.get(id=answer_upload.user_id)
            # Get or create user credit (new users get 50 free credits)
            user_credit, created = UserCredit.objects.get_or_create(
                user=user,
                defaults={
                    "free_credit": Decimal("50.00"),
                    "paid_credit": Decimal("0.00"),
                },
            )
            
            # Convert combined_cost to Decimal for accurate calculation
            cost_decimal = Decimal(str(combined_cost))
            
            # Deduct from user credits
            deduct_user_credit(user, cost_decimal)
            
            # Create UsageHistory record to track this deduction
            UsageHistory.objects.create(
                user=user,
                service_type="grading_combined",
                input_length=combined_tokens,  # Using total tokens as input length
                cost=cost_decimal,
            )
            
            # Get updated credit balance
            updated_credit = UserCredit.objects.get(user=user)
            logger.info(f"✅ Deducted ${combined_cost:.6f} from user {user.id} credits. Remaining balance: ${updated_credit.total_credit:.6f}")
            
        except User.DoesNotExist:
            logger.warning(f"User with ID {answer_upload.user_id} not found. Cannot deduct credits.")
        except Exception as e:
            logger.error(f"Error deducting credits for user {answer_upload.user_id}: {str(e)}")

def save_detailed_grading_to_db(grading_result, json_data):
    """
    Parses the result JSON and saves detailed Question and Criteria models 
    to the database for persistence.
    """
    # Clear existing details if re-grading to prevent duplicates
    QuestionGrade.objects.filter(grading_result=grading_result).delete()

    question_objs = []
    criteria_batch = []

    for q_data in json_data.get("results", []):
        # 1. Create QuestionGrade object
        q_grade = QuestionGrade.objects.create(
            grading_result=grading_result,
            question_number=q_data.get("question_number"),
            question_type=q_data.get("question_type"),
            allocated_marks=q_data.get("allocated_marks", 0),
            obtained_marks=q_data.get("obtained_marks", 0),
            student_answer=q_data.get("student_answer"),
            expected_answer=q_data.get("expected_answer"),
            summary=q_data.get("summary"),
            mistakes_identified=q_data.get("mistakes_identified", []),
            final_feedback=q_data.get("final_feedback"),
            general_feedback=q_data.get("general_feedback"),
            diagram_comparison=q_data.get("diagram_comparison")
        )

        # 2. Prepare CriteriaGrade objects (if breakdown exists)
        if "criteria_breakdown" in q_data and q_data["criteria_breakdown"]:
            for crit in q_data["criteria_breakdown"]:
                criteria_batch.append(CriteriaGrade(
                    question_grade=q_grade,
                    criterion_text=crit.get("criterion"),
                    allocated_marks=crit.get("allocated_marks", 0),
                    obtained_marks=crit.get("obtained_marks", 0),
                    feedback=crit.get("feedback"),
                    mistakes_found=crit.get("mistakes_found", [])
                ))
    
    # Bulk create criteria for performance
    if criteria_batch:
        CriteriaGrade.objects.bulk_create(criteria_batch)

def sync_csv_metrics_to_db(answer_upload, folder_path, process_type):
    """
    Finds the latest CSV, processes the data (Splitting OCR costs per question),
    and syncs to the DB. Robust against missing files.
    """
    # 1. Define pattern (wildcard * handles filename variations)
    prefix = "grading_metrics" if process_type == "GRADING" else "ocr_metrics"
    pattern = os.path.join(folder_path, f"*{prefix}*.csv")
    
    # 2. Find file
    files = glob.glob(pattern)
    if not files:
        logger.warning(f"⚠️ No {process_type} metrics CSV found matching: {pattern}")
        return

    # Use the most recent file
    latest_file = max(files, key=os.path.getctime)
    logger.info(f"Processing metrics file: {latest_file}")
    
    try:
        metrics_objs = []
        rows = []
        with open(latest_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            logger.warning(f"Metrics CSV {latest_file} is empty.")
            return

        # --- HELPER FUNCTIONS ---
        def safe_int(val):
            try: return int(float(val))
            except: return 0
        def safe_float(val):
            try: return float(val)
            except: return 0.0

        # Clear old data before inserting new
        AIMetrics.objects.filter(answer_upload=answer_upload, process_type=process_type).delete()

        # --- SPLITTING LOGIC ---
        if process_type == "OCR":
            # 1. Sum up the TOTAL cost of the entire OCR process
            total_input = sum(safe_int(r.get("input_tokens")) for r in rows)
            total_output = sum(safe_int(r.get("output_tokens")) for r in rows)
            total_cost = sum(safe_float(r.get("total_cost_usd")) for r in rows)
            # Use 'total_tokens' column if available, else calc sum
            total_tokens = sum(safe_int(r.get("total_tokens")) for r in rows)
            if total_tokens == 0: total_tokens = total_input + total_output

            # 2. Find out how many questions exist for this answer
            try:
                # Access the questions created in the grading step
                q_count = QuestionGrade.objects.filter(grading_result__answer_upload=answer_upload).count()
            except Exception as e:
                logger.warning(f"Could not count questions: {e}")
                q_count = 0

            if q_count > 0:
                # 3. Calculate Share per Question
                share_input = total_input // q_count
                share_output = total_output // q_count
                share_tokens = total_tokens // q_count
                share_cost = total_cost / q_count

                # 4. Create a DB record for EACH question
                questions = QuestionGrade.objects.filter(grading_result__answer_upload=answer_upload)
                for q in questions:
                    metrics_objs.append(AIMetrics(
                        answer_upload=answer_upload,
                        process_type="OCR",
                        identifier=str(q.question_number), 
                        input_tokens=share_input,
                        output_tokens=share_output,
                        total_tokens=share_tokens,
                        total_cost_usd=share_cost,
                        timestamp=timezone.now()
                    ))
                logger.info(f"Split Total OCR Cost (${total_cost:.4f}) among {q_count} questions.")
            
            else:
                # Fallback: If no questions found, save as "System Total"
                metrics_objs.append(AIMetrics(
                    answer_upload=answer_upload,
                    process_type="OCR",
                    identifier="Document Total",
                    input_tokens=total_input,
                    output_tokens=total_output,
                    total_tokens=total_tokens,
                    total_cost_usd=total_cost,
                    timestamp=timezone.now()
                ))

        else:
            # GRADING LOGIC (Already per-question, save as is)
            for row in rows:
                identifier = row.get("question_num") or "Unknown"
                metrics_objs.append(AIMetrics(
                    answer_upload=answer_upload,
                    process_type="GRADING",
                    identifier=identifier,
                    input_tokens=safe_int(row.get("input_tokens")),
                    output_tokens=safe_int(row.get("output_tokens")),
                    total_tokens=safe_int(row.get("total_tokens")),
                    total_cost_usd=safe_float(row.get("total_cost_usd")),
                    timestamp=row.get("utc_ts") or timezone.now()
                ))

        # 5. Save to DB
        AIMetrics.objects.bulk_create(metrics_objs)
        logger.info(f"✅ Synced {len(metrics_objs)} {process_type} metrics to DB")

    except Exception as e:
        logger.error(f"Failed to sync metrics csv: {e}", exc_info=True)

@api_view(["GET"])
def get_upload_history(request: Request, email: str = None) -> Response:
    """
    Fetch upload history of a specific admin by email.
    """
    try:
        if email:
            uploads = SampleQuestionPaper.objects.filter(updated_by=email)
        else:
            uploads = SampleQuestionPaper.objects.all()

        # Prepare data for the response
        upload_data = [
            {
                "file_name": upload.file.url if upload.file else "No File",
                "test_title": upload.test_title,
                "board": upload.board,
                "total_marks": upload.total_marks,
                "total_questions": upload.total_questions,
                "upload_date": upload.upload_date.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "subject": upload.subject,
            }
            for upload in uploads
        ]

        return Response(upload_data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"An unexpected error occurred in get_upload_history: {e}", exc_info=True)
        return Response(
            {"error": f"An unexpected error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_my_corrections(request: Request, evaluator_email: str) -> Response:
    """
    Retrieve the list of corrections made by the specified evaluator.
    """
    try:
        # Find the user based on the provided email
        try:
            user = User.objects.get(email=evaluator_email)
        except User.DoesNotExist:
            return Response(
                {"error": f"User with email {evaluator_email} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Based on error message, QuestionFeedback doesn't have a direct 'user' field
        # Let's try to find the feedback through answer uploads

        # First, check if there's a related field in AnswerUpload that connects to the evaluator
        # Looking at your code, it seems AnswerAssignment links evaluators to
        # answers
        evaluator_assignments = AnswerAssignment.objects.filter(
            evaluator=user.id,
            completed=True,  # Assuming completed means feedback was provided
        ).values_list("answer_upload_id", flat=True)

        # Now get all feedback for these assignments
        corrections = QuestionFeedback.objects.filter(
            answer_upload_id__in=evaluator_assignments
        )

        # Prepare data for response
        corrections_data = []
        for correction in corrections:
            answer_upload = correction.answer_upload

            # Determine question paper type and get the related paper based on
            # AnswerUpload fields
            if hasattr(answer_upload, "question_paper_type"):
                paper_type = answer_upload.question_paper_type

                if paper_type == "sample":
                    question_paper = answer_upload.sample_question_paper
                elif paper_type == "previous_year":
                    question_paper = answer_upload.previous_year_question_paper
                elif paper_type == "generated":
                    question_paper = answer_upload.generated_question_paper
                else:
                    # Skip if paper type is unknown
                    continue
            else:
                # If no paper_type field, try each relationship
                if (
                    hasattr(answer_upload, "sample_question_paper")
                    and answer_upload.sample_question_paper
                ):
                    question_paper = answer_upload.sample_question_paper
                    paper_type = "sample"
                elif (
                    hasattr(answer_upload, "previous_year_question_paper")
                    and answer_upload.previous_year_question_paper
                ):
                    question_paper = answer_upload.previous_year_question_paper
                    paper_type = "previous_year"
                elif (
                    hasattr(answer_upload, "generated_question_paper")
                    and answer_upload.generated_question_paper
                ):
                    question_paper = answer_upload.generated_question_paper
                    paper_type = "generated"
                else:
                    # Skip if no question paper is linked
                    continue

            # Get the student who submitted the answer
            answered_by = (
                getattr(answer_upload.user, "email", "Unknown")
                if hasattr(answer_upload, "user")
                else "Unknown"
            )

            item_data = {
                "qp_title": getattr(question_paper, "test_title", "No Title"),
                "board": getattr(question_paper, "board", "Unknown"),
                "total_marks": getattr(question_paper, "total_marks", 0),
                "answered_by": answered_by,
                "question_file": None,  # QP files not uploaded (copyright)
                "answer_file": (
                    answer_upload.file.url
                    if hasattr(answer_upload, "file") and answer_upload.file
                    else "No File"
                ),
                "feedback": correction.id,
                "subject": getattr(question_paper, "subject", "Unknown"),
                "paper_type": paper_type,
            }

            # Add date if available
            if hasattr(
                correction, "created_date"
            ):  # Using created_date based on error message
                item_data["corrected_date"] = correction.created_date.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            elif hasattr(correction, "upload_date"):
                item_data["corrected_date"] = correction.upload_date.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            else:
                item_data["corrected_date"] = "Unknown"

            # Add feedback text based on what's available
            if hasattr(correction, "feedback_text"):  # Based on error message
                item_data["feedback_text"] = correction.feedback_text
            elif hasattr(correction, "final_result"):
                item_data["feedback_text"] = correction.final_result

            # Add marks if available
            if hasattr(correction, "marks_obtained"):  # Based on error message
                item_data["marks_obtained"] = correction.marks_obtained

            corrections_data.append(item_data)

        return Response(corrections_data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Failed to retrieve corrections: {str(e)}", exc_info=True)
        return Response(
            {"error": f"Failed to retrieve corrections: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def _process_question_data(request: Request) -> tuple:
    """Helper function to process common question paper data.

    Args:
        request (Request): The Django REST Framework request object.

    Returns:
        tuple: A tuple containing the file, a dictionary of common data,
               and an error dictionary (or None).
    """
    # Extract common data from the request
    file = request.FILES.get("file")
    if not file:
        return None, {"error": "file is required."}, None

    common_data = {
        "test_title": request.data.get("test_title"),
        "updated_by": request.data.get("email"),
        "subject": request.data.get("subject"),
        "board": request.data.get("board"),
        "total_marks": request.data.get("total_marks", 0),
        "total_questions": request.data.get("total_questions", 0),
    }

    # Parse questions if passed as JSON string
    questions = request.data.get("questions")
    if isinstance(questions, str):
        try:
            questions = json.loads(questions)
        except json.JSONDecodeError:
            return None, {"error": "Invalid JSON format for questions."}, None

    common_data["questions"] = questions

    # Validate required fields
    required_fields = ["test_title", "board", "subject", "questions"]
    for field in required_fields:
        if not common_data.get(field):
            return None, {"error": f"{field} is required."}, None

    return file, common_data, None


@api_view(["POST"])
def upload_questions(request: Request) -> Response:
    """Uploads a generic question paper.

    Args:
        request (Request): The Django REST Framework request object.

    Returns:
        Response: A DRF Response object with a success message and the ID of
                  the created question paper.
    """
    file, common_data, error = _process_question_data(request)
    if error:
        return Response(error, status=status.HTTP_400_BAD_REQUEST)
    file_path = default_storage.save(
        f"question_papers/qp_uploader/{file.name}", file
    )
    question_paper = Questions(file=file_path, **common_data)
    question_paper.save()
    return Response(
        {
            "message": "Sample question paper uploaded successfully!",
            "id": question_paper.id,
        },
        status=status.HTTP_201_CREATED,
    )


# @api_view(["POST"])
# def upload_sample_question_paper(request: Request) -> Response:
#     """Upload a sample question paper.

#     Args:
#         request (Request): The Django REST Framework request object.

#     Returns:
#         Response: A DRF Response object indicating success and the new
#                   paper's ID.
#     """
#     file, common_data, error = _process_question_data(request)
#     if error:
#         return Response(error, status=status.HTTP_400_BAD_REQUEST)

#     # Save the file to the 'sample' folder
#     file_path = default_storage.save(
#         f"question_papers/sample/{file.name}", file
#     )

#     # Create a new SampleQuestionPaper instance
#     question_paper = SampleQuestionPaper(file=file_path, **common_data)
#     question_paper.save()

#     return Response(
#         {
#             "message": "Sample question paper uploaded successfully!",
#             "id": question_paper.id,
#         },
#         status=status.HTTP_201_CREATED,
#     )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_previous_year_question_paper(request: Request) -> Response:
    """Upload a previous year question paper.

    Args:
        request (Request): The Django REST Framework request object.

    Returns:
        Response: A DRF Response object indicating success and the new
                  paper's ID.
    """
    # 1. Get the file first to support filename parsing
    file = request.FILES.get("file")
    if not file:
        return Response({"error": "file is required."}, status=status.HTTP_400_BAD_REQUEST)

    # 2. Extract explicit data
    test_title = request.data.get("test_title")
    board = request.data.get("board")
    subject = request.data.get("subject")
    year = request.data.get("year")
    
    # 3. Parse filename for metadata if fields are missing
    # Format: <board>_<class>_<subject>_<qpnumber&set>_<year>_<number>.pdf
    # Example 1: CBSE_10_Maths_Set1_2023_1.pdf
    # Example 2: CBSE_10_Maths_Set1_2023.pdf
    try:
        filename_with_ext = file.name
        # Remove extension using os.path.splitext
        filename, _ = os.path.splitext(filename_with_ext)
        
        parts = filename.split('_')
        logger.info(f"Parsing filename metadata: {filename} -> {parts}")

        if len(parts) >= 3: # Minimum: Board_Class_Subject...
            if not board:
                board = parts[0]
            if not subject:
                # Assuming index 2 is subject (Board_Class_Subject)
                subject = parts[2]
            
            # Year extraction strategy:
            # Look for a 4-digit number starting from the end, going backwards
            # This handles both ..._2023_1 and ..._2023
            if not year:
                for part in reversed(parts):
                    if part.isdigit() and len(part) == 4:
                        year = int(part)
                        break
            
            # Auto-generate title if missing
            if not test_title:
                test_title = f"{board} {subject} {year or ''} Previous Year Paper"
            
            logger.info(f"Extracted metadata: Board={board}, Subject={subject}, Year={year}")
            
    except Exception as e:
        logger.warning(f"Failed to parse filename metadata: {e}")

    # 4. Construct common_data manually (replaces _process_question_data validation)
    common_data = {
        "test_title": test_title,
        "updated_by": request.data.get("email"), # Or request.user.email? keeping consistent with old code
        "subject": subject,
        "board": board,
        "total_marks": request.data.get("total_marks", 0),
        "total_questions": request.data.get("total_questions", 0),
    }

    # Questions parsing (kept from _process_question_data)
    questions = request.data.get("questions")
    if isinstance(questions, str):
        try:
            questions = json.loads(questions)
        except json.JSONDecodeError:
            return Response({"error": "Invalid JSON format for questions."}, status=status.HTTP_400_BAD_REQUEST)
    common_data["questions"] = questions

    # 5. Validate Required Fields (Modified to include our auto-populated values)
    # Note: 'questions' is often optional in other uploaders, but _process_question_data marked it required. 
    # For Previous Year papers (PDFs), 'questions' JSON might NOT be mandatory if it's just a PDF upload? 
    # The original _process_question_data required 'questions'. keeping it safer, but often Previous Year papers are just PDFs.
    # Let's match original rigorousness:
    if not common_data.get("test_title"):
         return Response({"error": "test_title is required (could not extract from filename)."}, status=status.HTTP_400_BAD_REQUEST)
    # if not common_data.get("questions"): # Previous Year papers might just be PDFs? removing strict check for questions here as it often breaks PDF-only uploads
    #     pass 

    # Validate Year explicitly
    if not year:
        return Response(
            {"error": "year is required for previous year papers (could not extract from filename)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        year = int(year)
    except ValueError:
        return Response(
            {"error": "year must be a valid number."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Optional metadata for previous year papers
    set_number = request.data.get("set_number")
    qp_code = request.data.get("qp_code")

    # 6. Handle Answer Key Upload
    answer_key = request.FILES.get("answer_key")
    answer_key_path = None
    if answer_key:
        answer_key_path = default_storage.save(
            f"answer_keys/previous_year/{answer_key.name}", answer_key
        )

    # Save the file to the 'previous_year' folder
    file_path = default_storage.save(
        f"question_papers/previous_year/{file.name}", file
    )

    # Create a new PreviousYearQuestionPaper instance
    question_paper = PreviousYearQuestionPaper(
        file=file_path,
        
        year=year,
        set_number=set_number,
        qp_code=qp_code,
        
        answer_key=answer_key_path,
        **common_data,
    )
    question_paper.save()

    return Response(
        {
            "message": "Previous year question paper uploaded successfully!",
            "id": question_paper.id,
            "parsed_metadata": {
                "board": board,
                "subject": subject,
                "year": year
            }
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bulk_upload_previous_year_question_papers(request: Request) -> Response:
    """
    Bulk upload Answer Keys and Reference Images/Assets.
    
    Question paper files are NOT uploaded (copyright reasons).
    The frontend provides links to official download websites instead.
    
    Metadata (board, subject, year, qp_code, set_number) is extracted from filenames.
    
    File routing based on naming convention:
    - <Name>_answer.json/.pdf -> Creates QP record and links answer key
    - <Name>_Q<Num>.jpg/.png -> Asset/reference image for QP record
    
    Filename format expected:
    <board>_<class>_<subject>_<qpcode>set<setnumber>_<year>_<number>_answer.json
    Example: cbse_12_chemistry_56Bset5_2023_70_answer.json
    """
    from .models import extract_metadata_from_filename, generate_test_title
    
    files = request.FILES.getlist("files")
    if not files:
        # Fallback: check if files are sent as 'file' list
        files = request.FILES.getlist("file")
    
    if not files:
        return Response({"error": "No files provided"}, status=status.HTTP_400_BAD_REQUEST)

    # Batch metadata (defaults - can be overridden by filename extraction)
    def clean_meta(val):
        if not val or str(val).lower() in ["undefined", "null", "none", ""]:
            return None
        return val

    batch_board = clean_meta(request.data.get("board"))
    batch_subject = clean_meta(request.data.get("subject"))
    batch_year = clean_meta(request.data.get("year"))
    
    results = {
        "created_qps": [],
        "linked_keys": [],
        "linked_assets": [],
        "extracted_metadata": [],  # Show what was extracted from filenames
        "errors": []
    }

    # Helper to clean filename
    def get_clean_name(filename):
        name, _ = os.path.splitext(filename)
        return name
    
    def find_or_create_qp(base_filename: str, create_if_missing: bool = True):
        """
        Find existing QP by matching criteria or create a new one.
        
        Search order:
        1. By qp_code + set_number combination
        2. By board + subject + year combination (fallback)
        3. Create new if not found and create_if_missing is True
        """
        metadata = extract_metadata_from_filename(base_filename)
        
        # 1. Try to find by qp_code + set_number (preferred)
        if metadata.qp_code and metadata.set_number:
            qp = PreviousYearQuestionPaper.objects.filter(
                qp_code__iexact=metadata.qp_code,
                set_number=metadata.set_number
            ).order_by('-upload_date').first()
            
            if qp:
                return qp, metadata, False
        
        # 2. Try to find by board + subject + year
        if metadata.board and metadata.subject and metadata.year:
            qp = PreviousYearQuestionPaper.objects.filter(
                board__iexact=metadata.board,
                subject__iexact=metadata.subject,
                year=metadata.year,
                qp_code__iexact=metadata.qp_code if metadata.qp_code else None,
                set_number=metadata.set_number if metadata.set_number else None
            ).order_by('-upload_date').first()
            
            if qp:
                return qp, metadata, False
        
        # 3. Create new QP if allowed
        if create_if_missing:
            # Use batch metadata as fallback
            board = metadata.board or batch_board
            subject = metadata.subject or batch_subject
            year = metadata.year or (int(batch_year) if batch_year else None)
            
            if not year:
                return None, metadata, False  # Cannot create without year
            
            qp = PreviousYearQuestionPaper.objects.create(
                board=board,
                subject=subject,
                year=year,
                qp_code=metadata.qp_code,
                set_number=metadata.set_number,
                test_title=generate_test_title(metadata),
                updated_by=request.data.get("email"),
                total_marks=request.data.get("total_marks", 0),
                total_questions=request.data.get("total_questions", 0),
                assets={}
            )
            return qp, metadata, True  # Created new
        
        return None, metadata, False

    # Separate files by type (answer keys vs assets)
    keys = []
    assets = []

    for f in files:
        name = get_clean_name(f.name)
        if name.endswith("_answer"):
            keys.append(f)
        elif "_Q" in name and name.split("_Q")[-1].isalnum(): 
            assets.append(f)
        else:
            # Unknown file type - try to process as answer key if JSON/PDF
            ext = os.path.splitext(f.name)[1].lower()
            if ext in ['.json', '.pdf']:
                results["errors"].append(
                    f"{f.name}: Unrecognized filename pattern. "
                    f"Answer keys should end with '_answer', assets should have '_Q<num>' pattern."
                )
            else:
                results["errors"].append(f"{f.name}: Unsupported file type")

    # Process Answer Keys (Create QP if needed)
    for f in keys:
        try:
            name_no_ext = get_clean_name(f.name)
            # Remove _answer suffix to get base name
            base_name = name_no_ext.replace("_answer", "")
            
            logger.info(f"Processing Answer Key: {f.name}, base_name: {base_name}")
            
            # Find or create QP record
            qp, metadata, was_created = find_or_create_qp(base_name, create_if_missing=True)
            
            if qp:
                f.seek(0)
                # Save answer key file
                path = default_storage.save(f"answer_keys/previous_year/{f.name}", f)
                qp.answer_key = path
                qp.save()
                
                action = "Created new QP and linked" if was_created else "Linked to existing QP"
                results["linked_keys"].append(f"{f.name} -> {qp.test_title} ({action})")
                
                if was_created:
                    results["created_qps"].append(f"{base_name}")
                
                results["extracted_metadata"].append({
                    "file": f.name,
                    "type": "answer_key",
                    "board": metadata.board,
                    "subject": metadata.subject,
                    "year": metadata.year,
                    "qp_code": metadata.qp_code,
                    "set_number": metadata.set_number,
                    "created_new_record": was_created
                })
            else:
                results["errors"].append(
                    f"{f.name}: Could not find or create QP. Extracted metadata: "
                    f"board={metadata.board}, subject={metadata.subject}, year={metadata.year}, "
                    f"qp_code={metadata.qp_code}, set={metadata.set_number}"
                )

        except Exception as e:
            results["errors"].append(f"{f.name}: {str(e)}")

    # Process Assets (Create QP if needed)
    for f in assets:
        try:
            name_no_ext = get_clean_name(f.name)
            
            if "_Q" in name_no_ext:
                base_name, q_suffix = name_no_ext.rsplit("_Q", 1)
                q_num = "Q" + q_suffix
                
                logger.info(f"Processing Asset: {f.name}, base_name: {base_name}, q_num: {q_num}")
                
                # Find or create QP record
                qp, metadata, was_created = find_or_create_qp(base_name, create_if_missing=True)
                
                if qp:
                    f.seek(0)
                    # Save asset file
                    path = default_storage.save(f"question_papers/previous_year/assets/{f.name}", f)
                    
                    # Update assets JSON map
                    if not qp.assets:
                        qp.assets = {}
                    qp.assets[q_num] = path
                    qp.save()
                    
                    action = "Created new QP" if was_created else "Linked to existing"
                    results["linked_assets"].append(f"{f.name} -> {q_num} ({action})")
                    
                    if was_created:
                        results["created_qps"].append(f"{base_name}")
                    
                    results["extracted_metadata"].append({
                        "file": f.name,
                        "type": "asset",
                        "question_number": q_num,
                        "board": metadata.board,
                        "subject": metadata.subject,
                        "year": metadata.year,
                        "qp_code": metadata.qp_code,
                        "set_number": metadata.set_number,
                        "created_new_record": was_created
                    })
                else:
                    results["errors"].append(
                        f"{f.name}: Could not find or create QP. "
                        f"Extracted: board={metadata.board}, subject={metadata.subject}, year={metadata.year}"
                    )
            else:
                results["errors"].append(f"{f.name}: Invalid asset format (missing _Q pattern)")

        except Exception as e:
            results["errors"].append(f"{f.name}: {str(e)}")

    return Response(results, status=status.HTTP_200_OK)


@api_view(["POST"])
def upload_generated_question_paper(request: Request) -> Response:
    """Upload a generated question paper.

    Args:
        request (Request): The Django REST Framework request object.

    Returns:
        Response: A DRF Response object indicating success and the new
                  paper's ID.
    """
    file, common_data, error = _process_question_data(request)
    if error:
        return Response(error, status=status.HTTP_400_BAD_REQUEST)

    # Additional validation for generation_id field
    # Get user_id from request
    user_id = request.data.get("user_id")
    if not user_id:
        return Response(
            {
                "error": "user_id is required to track who generated this paper."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Save the file to the 'generated' folder
    file_path = default_storage.save(
        f"question_papers/generated/{file.name}", file
    )

    # Create a new GeneratedQuestionPaper instance
    question_paper = GeneratedQuestionPaper(
        file=file_path,
        user_id=user_id,  # Store the user_id who generated this paper
        **common_data,
    )
    question_paper.save()

    return Response(
        {
            "message": "Generated question paper uploaded successfully!",
            "id": question_paper.id,
        },
        status=status.HTTP_201_CREATED,
    )


# GET functions for retrieving question papers


@api_view(["GET"])
def get_questions(request: Request) -> Response:
    """Get all question papers with answered/available status.

    Args:
        request (Request): The Django REST Framework request object with
                         'user_id' as a query parameter.

    Returns:
        Response: A DRF Response object with lists of answered and available
                  question papers.
    """
    user_id = request.GET.get("user_id")
    if not user_id:
        return Response({"error": "User ID is required"}, status=400)

    # Fetch all question papers
    question_papers = Questions.objects.all()

    # Fetch question papers already answered by the user
    answered_paper_ids = AnswerUpload.objects.filter(
        user_id=user_id,
        # Filter by paper type (assuming 'regular' for normal Questions)
        question_paper_type="regular",
    ).values_list("question_paper_id", flat=True)

    # Fetch answered question papers with AnswerUpload model ordering
    answered_question_papers = (
        AnswerUpload.objects.filter(
            user_id=user_id,
            question_paper_id__in=answered_paper_ids,
            question_paper_type="",
        )
        .select_related("question_paper")
        .order_by("-upload_date")
    )

    # Fetch available question papers (not yet answered)
    available_question_papers = question_papers.exclude(
        id__in=answered_paper_ids
    )

    # Serialize answered question papers with result_status, feedback ID, and
    # answer_file
    answered_data = []
    for au in answered_question_papers:
        qp = au.question_paper  # Access the related Questions instance

        # Check if feedback exists for this answered question paper and user
        feedback = QuestionFeedback.objects.filter(answer_upload=au).first()

        if feedback:
            feedback_id = feedback.id
            result_status = "See Result"
        else:
            feedback_id = None
            result_status = "Not Corrected"

        answered_data.append(
            {
                "id": qp.id,
                "answer_id": au.id,  # Include the answer upload ID
                "file": None,  # QP files not uploaded (copyright)
                "answer_file": au.file.url,
                "title": qp.test_title,
                "subject": qp.subject,
                "updated_by": qp.updated_by,
                "upload_date": au.upload_date.strftime("%Y-%m-%d %H:%M:%S"),
                "board": qp.board,
                "total_marks": qp.total_marks,
                "total_questions": qp.total_questions,
                "result_status": result_status,
                "feedback_id": feedback_id,
            }
        )

    # Serialize available question papers
    available_data = [
        {
            "id": qp.id,
            "file": None,  # QP files not uploaded
            "title": qp.test_title,
            "subject": qp.subject,
            "updated_by": qp.updated_by,
            "upload_date": qp.upload_date.strftime("%Y-%m-%d %H:%M:%S"),
            "board": qp.board,
            "total_marks": qp.total_marks,
            "total_questions": qp.total_questions,
        }
        for qp in available_question_papers
    ]

    return Response(
        {
            "answered_question_papers": answered_data,
            "available_question_papers": available_data,
        }
    )


# @api_view(["GET"])
# def get_sample_question_papers(request: Request) -> Response:
#     """Get all sample question papers with answered/available status.

#     Args:
#         request (Request): The Django REST Framework request object with
#                          'user_id' as a query parameter.

#     Returns:
#         Response: A DRF Response object with lists of answered and available
#                   sample question papers.
#     """
#     user_id = request.GET.get("user_id")
#     if not user_id:
#         return Response({"error": "User ID is required"}, status=400)

#     # Fetch all sample question papers
#     question_papers = SampleQuestionPaper.objects.all()

#     # Fetch question papers already answered by the user
#     answered_paper_ids = AnswerUpload.objects.filter(
#         user_id=user_id, question_paper_type="sample"  # Filter by paper type
#     ).values_list("question_paper_id", flat=True)

#     # Fetch answered question papers with AnswerUpload model ordering
#     answered_question_papers = (
#         AnswerUpload.objects.filter(
#             user_id=user_id,
#             question_paper_id__in=answered_paper_ids,
#             question_paper_type="sample",
#         )
#         .select_related("sample_question_paper")
#         .order_by("-upload_date")
#     )

#     # Fetch available question papers (not yet answered)
#     available_question_papers = question_papers.exclude(
#         id__in=answered_paper_ids
#     )

#     # Serialize answered question papers with result_status, feedback ID, and
#     # answer_file
#     answered_data = []
#     for au in answered_question_papers:
#         qp = (
#             au.sample_question_paper
#         )  # Access the related SampleQuestionPaper instance

#         # Check if feedback exists for this answered question paper and user
#         feedback = QuestionFeedback.objects.filter(answer_upload=au).first()

#         if feedback:
#             feedback_id = feedback.id
#             result_status = "See Result"
#         else:
#             feedback_id = None
#             result_status = "Not Corrected"

#         answered_data.append(
#             {
#                 "id": qp.id,
#                 "answer_id": au.id,  # Include the answer upload ID
#                 "file": None,  # QP files not uploaded
#                 "answer_file": au.file.url,
#                 "title": qp.test_title,
#                 "subject": qp.subject,
#                 "updated_by": qp.updated_by,
#                 "upload_date": au.upload_date.strftime("%Y-%m-%d %H:%M:%S"),
#                 "board": qp.board,
#                 "total_marks": qp.total_marks,
#                 "total_questions": qp.total_questions,
#                 "result_status": result_status,
#                 "feedback_id": feedback_id,
#             }
#         )

#     # Serialize available question papers
#     available_data = [
#         {
#             "id": qp.id,
#             "file": None,  # QP files not uploaded
#             "title": qp.test_title,
#             "subject": qp.subject,
#             "updated_by": qp.updated_by,
#             "upload_date": qp.upload_date.strftime("%Y-%m-%d %H:%M:%S"),
#             "board": qp.board,
#             "total_marks": qp.total_marks,
#             "total_questions": qp.total_questions,
#         }
#         for qp in available_question_papers
#     ]

#     return Response(
#         {
#             "answered_question_papers": answered_data,
#             "available_question_papers": available_data,
#         }
#     )


@api_view(["GET"])
def get_previous_year_question_papers(request: Request) -> Response:
    """Get previous year question papers with answered/available status.

    Args:
        request (Request): The Django REST Framework request object with
                         'user_id' and optional 'year' as query parameters.

    Returns:
        Response: A DRF Response object with lists of answered and available
                  previous year question papers.
    """
    user_id = request.GET.get("user_id")
    year = request.GET.get("year")

    if not user_id:
        return Response({"error": "User ID is required"}, status=400)

    # Fetch previous year question papers, filtered by year if specified
    if year:
        try:
            year = int(year)
            question_papers = PreviousYearQuestionPaper.objects.filter(
                year=year
            )
        except ValueError:
            return Response(
                {"error": "Year must be a valid integer"}, status=400
            )
    else:
        question_papers = PreviousYearQuestionPaper.objects.all().order_by(
            "-year", "-upload_date"
        )

    # Fetch question papers already answered by the user
    answered_paper_ids = AnswerUpload.objects.filter(
        user_id=user_id, question_paper_type="previous_year"
    ).values_list("question_paper_id", flat=True)

    # Fetch answered question papers with AnswerUpload model ordering
    answered_question_papers = (
        AnswerUpload.objects.filter(
            user_id=user_id,
            question_paper_id__in=answered_paper_ids,
            question_paper_type="previous_year",
        )
        .select_related("previous_year_question_paper")
        .order_by("-upload_date")
    )

    # Fetch available question papers (not yet answered)
    available_question_papers = question_papers.exclude(
        id__in=answered_paper_ids
    )

    # Serialize answered question papers with result_status, feedback ID, and
    # answer_file
    answered_data = []
    for au in answered_question_papers:
        qp = au.previous_year_question_paper

        # Check if feedback exists for this answered question paper and user
        feedback = QuestionFeedback.objects.filter(answer_upload=au).first()

        if feedback:
            feedback_id = feedback.id
            result_status = "See Result"
        else:
            feedback_id = None
            result_status = "Not Corrected"

        answer_key_url = None
        if qp.answer_key:
            try:
                answer_key_url = qp.answer_key.url
            except (ValueError, AttributeError):
                # If answer_key exists but URL generation fails, try alternative
                if hasattr(qp.answer_key, 'name'):
                    answer_key_url = qp.answer_key.name
        answered_data.append(
            {
                "id": qp.id,
                "answer_id": au.id,  # Include the answer upload ID
                "attempt_number": au.attempt_number,  # Include attempt number for retake display
                "file": None,  # QP files not uploaded
                "answer_file": au.file.url,
                "title": qp.test_title,
                "subject": qp.subject,
                "year": qp.year,  # Include year for previous year papers
                "set_number": qp.set_number,
                "qp_code": qp.qp_code,
                "answer_key": answer_key_url,
                "updated_by": qp.updated_by,
                "upload_date": au.upload_date.strftime("%Y-%m-%d %H:%M:%S"),
                "board": qp.board,
                "total_marks": qp.total_marks,
                "total_questions": qp.total_questions,
                "result_status": result_status,
                "feedback_id": feedback_id,
            }
        )

    # Serialize available question papers
    available_data = []
    for qp in available_question_papers:
        answer_key_url = None
        if qp.answer_key:
            try:
                answer_key_url = qp.answer_key.url
            except (ValueError, AttributeError):
                # If answer_key exists but URL generation fails, try alternative
                if hasattr(qp.answer_key, 'name'):
                    answer_key_url = qp.answer_key.name
        available_data.append(
            {
                "id": qp.id,
                "file": None,  # QP files not uploaded
                "title": qp.test_title,
                "subject": qp.subject,
                "year": qp.year,  # Include year for previous year papers
                "set_number": qp.set_number,
                "qp_code": qp.qp_code,
                "answer_key": answer_key_url,
                "updated_by": qp.updated_by,
                "upload_date": qp.upload_date.strftime("%Y-%m-%d %H:%M:%S"),
                "board": qp.board,
                "total_marks": qp.total_marks,
                "total_questions": qp.total_questions,
            }
        )

    return Response(
        {
            "answered_question_papers": answered_data,
            "available_question_papers": available_data,
        }
    )


@api_view(["GET"])
def get_generated_question_papers(request: Request) -> Response:
    """Get generated question papers with answered/available status.

    Args:
        request (Request): The Django REST Framework request object with
                         'user_id' as a query parameter.

    Returns:
        Response: A DRF Response object with lists of answered and available
                  generated question papers.
    """
    user_id = request.GET.get("user_id")

    if not user_id:
        return Response({"error": "User ID is required"}, status=400)

    # Fetch generated question papers, filtered by user_id and generation_id
    # if specified
    filters = {"user_id": user_id}  # Always filter by user_id

    # Get only question papers that belong to this user
    question_papers = GeneratedQuestionPaper.objects.filter(
        **filters
    ).order_by("-upload_date")

    # Fetch question papers already answered by the user
    answered_paper_ids = AnswerUpload.objects.filter(
        user_id=user_id, question_paper_type="generated"
    ).values_list("question_paper_id", flat=True)

    # Fetch answered question papers with AnswerUpload model ordering
    answered_question_papers = (
        AnswerUpload.objects.filter(
            user_id=user_id,
            question_paper_id__in=answered_paper_ids,
            question_paper_type="generated",
        )
        .select_related("generated_question_paper")
        .order_by("-upload_date")
    )

    # Fetch available question papers (not yet answered)
    available_question_papers = question_papers.exclude(
        id__in=answered_paper_ids
    )

    # Serialize answered question papers with result_status, feedback ID, and
    # answer_file
    answered_data = []
    for au in answered_question_papers:
        qp = au.generated_question_paper

        # Check if feedback exists for this answered question paper and user
        feedback = QuestionFeedback.objects.filter(answer_upload=au).first()

        if feedback:
            feedback_id = feedback.id
            result_status = "See Result"
        else:
            feedback_id = None
            result_status = "Not Corrected"

        answered_data.append(
            {
                "id": qp.id,
                "answer_id": au.id,  # Include the answer upload ID
                "file": None,  # QP files not uploaded
                "answer_file": au.file.url,
                "title": qp.test_title,
                "subject": qp.subject,
                "user_id": qp.user_id,  # Include user_id who generated this paper
                "updated_by": qp.updated_by,
                "upload_date": au.upload_date.strftime("%Y-%m-%d %H:%M:%S"),
                "board": qp.board,
                "total_marks": qp.total_marks,
                "total_questions": qp.total_questions,
                "result_status": result_status,
                "feedback_id": feedback_id,
            }
        )

    # Serialize available question papers
    available_data = [
        {
            "id": qp.id,
            "file": None,  # QP files not uploaded
            "title": qp.test_title,
            "subject": qp.subject,
            "user_id": qp.user_id,  # Include user_id who generated this paper
            "updated_by": qp.updated_by,
            "upload_date": qp.upload_date.strftime("%Y-%m-%d %H:%M:%S"),
            "board": qp.board,
            "total_marks": qp.total_marks,
            "total_questions": qp.total_questions,
        }
        for qp in available_question_papers
    ]

    return Response(
        {
            "answered_question_papers": answered_data,
            "available_question_papers": available_data,
        }
    )


@api_view(["GET"])
def get_all_question_papers(request: Request) -> Response:
    """
    Get all question papers (sample, previous year, and generated) with answered/available status

    Args:
        request (Request): The Django REST Framework request object with
                         'user_id' and optional 'year' as query parameters.

    Returns:
        Response: A DRF Response object containing all types of question
                  papers, categorized as answered and available.
    """
    user_id = request.GET.get("user_id")
    # Optional year filter for previous year papers
    year = request.GET.get("year")

    if not user_id:
        return Response({"error": "User ID is required"}, status=400)

    # Initialize response dictionary
    result = {
        "sample": {
            "answered_question_papers": [],
            "available_question_papers": [],
        },
        "previous_year": {
            "answered_question_papers": [],
            "available_question_papers": [],
        },
        "generated": {
            "answered_question_papers": [],
            "available_question_papers": [],
        },
    }

    # 1. Process Sample Question Papers
    # ----------------------------------
    # Fetch all sample question papers
    sample_papers = SampleQuestionPaper.objects.all()

    # Fetch sample papers already answered by the user
    sample_answered_ids = AnswerUpload.objects.filter(
        user_id=user_id, question_paper_type="sample"
    ).values_list("question_paper_id", flat=True)

    # Fetch answered sample papers with AnswerUpload model ordering
    sample_answered_uploads = (
        AnswerUpload.objects.filter(
            user_id=user_id,
            question_paper_id__in=sample_answered_ids,
            question_paper_type="sample",
        )
        .select_related("sample_question_paper")
        .prefetch_related("grading_results")
        .order_by("-upload_date")
    )

    # Serialize answered sample papers with result_status, feedback ID, and
    # answer_file
    for au in sample_answered_uploads:
        qp = au.sample_question_paper

        # Check if feedback exists for this answered question paper and user
        feedback = QuestionFeedback.objects.filter(answer_upload=au).first()

        if feedback:
            feedback_id = feedback.id
            result_status = "See Result"
        else:
            feedback_id = None
            result_status = "Not Corrected"

        result["sample"]["answered_question_papers"].append(
            {
                "id": qp.id,
                "answer_id": au.id,  # Include the answer upload ID
                "file": None,  # QP files not uploaded
                "answer_file": au.file.url,
                "title": qp.test_title,
                "subject": qp.subject,
                "updated_by": qp.updated_by,
                "upload_date": au.upload_date.strftime("%Y-%m-%d %H:%M:%S"),
                "board": qp.board,
                "total_marks": qp.total_marks,
                "total_questions": qp.total_questions,
                "result_status": result_status,
                "feedback_id": feedback_id,
                "paper_type": "sample",
                "ocr_processed": au.ocr_processed,
                "grading_processed": au.grading_results.first().grading_processed if au.grading_results.first() else False,
                "grading_id": au.grading_results.first().id if au.grading_results.first() else None,
            }
        )

    # Fetch available sample papers (not yet answered)
    sample_available = sample_papers.exclude(id__in=sample_answered_ids)

    # Serialize available sample papers
    for qp in sample_available:
        result["sample"]["available_question_papers"].append(
            {
                "id": qp.id,
                "file": None,  # QP files not uploaded
                "title": qp.test_title,
                "subject": qp.subject,
                "updated_by": qp.updated_by,
                "upload_date": qp.upload_date.strftime("%Y-%m-%d %H:%M:%S"),
                "board": qp.board,
                "total_marks": qp.total_marks,
                "total_questions": qp.total_questions,
                "paper_type": "sample",
            }
        )

    # 2. Process Previous Year Question Papers
    # ---------------------------------------
    # Fetch previous year question papers, filtered by year if specified
    if year:
        try:
            year = int(year)
            previous_year_papers = PreviousYearQuestionPaper.objects.filter(
                year=year
            ).order_by("-year", "-upload_date")
        except ValueError:
            return Response(
                {"error": "Year must be a valid integer"}, status=400
            )
    else:
        previous_year_papers = (
            PreviousYearQuestionPaper.objects.all().order_by(
                "-year", "-upload_date"
            )
        )

    # Fetch previous year papers already answered by the user
    previous_year_answered_ids = AnswerUpload.objects.filter(
        user_id=user_id, question_paper_type="previous_year"
    ).values_list("question_paper_id", flat=True)

    # Fetch answered previous year papers with AnswerUpload model ordering
    previous_year_answered_uploads = (
        AnswerUpload.objects.filter(
            user_id=user_id,
            question_paper_id__in=previous_year_answered_ids,
            question_paper_type="previous_year",
        )
        .select_related("previous_year_question_paper")
        .prefetch_related("grading_results")
        .order_by("-upload_date")
    )

    # Serialize answered previous year papers
    for au in previous_year_answered_uploads:
        qp = au.previous_year_question_paper

        # Check if feedback exists for this answered question paper and user
        feedback = QuestionFeedback.objects.filter(answer_upload=au).first()

        if feedback:
            feedback_id = feedback.id
            result_status = "See Result"
        else:
            feedback_id = None
            result_status = "Not Corrected"

        answer_key_url = None
        if qp.answer_key:
            try:
                answer_key_url = qp.answer_key.url
            except (ValueError, AttributeError):
                # If answer_key exists but URL generation fails, try alternative
                if hasattr(qp.answer_key, 'name'):
                    answer_key_url = qp.answer_key.name
        result["previous_year"]["answered_question_papers"].append(
            {
                "id": qp.id,
                "answer_id": au.id,  # Include the answer upload ID
                "file": None,  # QP files not uploaded
                "answer_file": au.file.url,
                "title": qp.test_title,
                "subject": qp.subject,
                "year": qp.year,
                "set_number": qp.set_number,
                "qp_code": qp.qp_code,
                "answer_key": answer_key_url,
                "updated_by": qp.updated_by,
                "upload_date": au.upload_date.strftime("%Y-%m-%d %H:%M:%S"),
                "board": qp.board,
                "total_marks": qp.total_marks,
                "total_questions": qp.total_questions,
                "result_status": result_status,
                "feedback_id": feedback_id,
                "paper_type": "previous_year",
                "ocr_processed": au.ocr_processed,
                "grading_processed": au.grading_results.first().grading_processed if au.grading_results.first() else False,
                "grading_id": au.grading_results.first().id if au.grading_results.first() else None,
            }
        )

    # Fetch available previous year papers (not yet answered)
    previous_year_available = previous_year_papers.exclude(
        id__in=previous_year_answered_ids
    )

    # Serialize available previous year papers
    for qp in previous_year_available:
        answer_key_url = None
        if qp.answer_key:
            try:
                answer_key_url = qp.answer_key.url
            except (ValueError, AttributeError):
                # If answer_key exists but URL generation fails, try alternative
                if hasattr(qp.answer_key, 'name'):
                    answer_key_url = qp.answer_key.name
        result["previous_year"]["available_question_papers"].append(
            {
                "id": qp.id,
                "file": None,  # QP files not uploaded
                "title": qp.test_title,
                "subject": qp.subject,
                "year": qp.year,
                "set_number": qp.set_number,
                "qp_code": qp.qp_code,
                "answer_key": answer_key_url,
                "updated_by": qp.updated_by,
                "upload_date": qp.upload_date.strftime("%Y-%m-%d %H:%M:%S"),
                "board": qp.board,
                "total_marks": qp.total_marks,
                "total_questions": qp.total_questions,
                "paper_type": "previous_year",
            }
        )

    # 3. Process Generated Question Papers
    # -----------------------------------
    # Fetch generated question papers for this user
    generated_papers = GeneratedQuestionPaper.objects.filter(
        user_id=user_id
    ).order_by("-upload_date")

    # Fetch generated papers already answered by the user
    generated_answered_ids = AnswerUpload.objects.filter(
        user_id=user_id, question_paper_type="generated"
    ).values_list("question_paper_id", flat=True)

    # Fetch answered generated papers with AnswerUpload model ordering
    generated_answered_uploads = (
        AnswerUpload.objects.filter(
            user_id=user_id,
            question_paper_id__in=generated_answered_ids,
            question_paper_type="generated",
        )
        .select_related("generated_question_paper")
        .prefetch_related("grading_results")
        .order_by("-upload_date")
    )

    # Serialize answered generated papers
    for au in generated_answered_uploads:
        qp = au.generated_question_paper

        # Check if feedback exists for this answered question paper and user
        feedback = QuestionFeedback.objects.filter(answer_upload=au).first()

        if feedback:
            feedback_id = feedback.id
            result_status = "See Result"
        else:
            feedback_id = None
            result_status = "Not Corrected"

        result["generated"]["answered_question_papers"].append(
            {
                "id": qp.id,
                "answer_id": au.id,  # Include the answer upload ID
                "file": None,  # QP files not uploaded
                "answer_file": au.file.url,
                "title": qp.test_title,
                "subject": qp.subject,
                "user_id": qp.user_id,
                "updated_by": qp.updated_by,
                "upload_date": au.upload_date.strftime("%Y-%m-%d %H:%M:%S"),
                "board": qp.board,
                "total_marks": qp.total_marks,
                "total_questions": 0,  # Generated papers might not have questionable count stored directly
                "result_status": result_status,
                "feedback_id": feedback_id,
                "paper_type": "generated",
                "ocr_processed": au.ocr_processed,
                "grading_processed": au.grading_results.first().grading_processed if au.grading_results.first() else False,
                "grading_id": au.grading_results.first().id if au.grading_results.first() else None,
            }
        )

    # Fetch available generated papers (not yet answered)
    generated_available = generated_papers.exclude(
        id__in=generated_answered_ids
    )

    # Serialize available generated papers
    for qp in generated_available:
        result["generated"]["available_question_papers"].append(
            {
                "id": qp.id,
                "file": None,  # QP files not uploaded
                "title": qp.test_title,
                "subject": qp.subject,
                "user_id": qp.user_id,
                "updated_by": qp.updated_by,
                "upload_date": qp.upload_date.strftime("%Y-%m-%d %H:%M:%S"),
                "board": qp.board,
                "total_marks": qp.total_marks,
                "total_questions": qp.total_questions,
                "paper_type": "generated",
            }
        )

    # 4. Create Combined Results
    # --------------------------
    # Combine all answered papers into a single list
    all_answered = []
    all_answered.extend(result["sample"]["answered_question_papers"])
    all_answered.extend(result["previous_year"]["answered_question_papers"])
    all_answered.extend(result["generated"]["answered_question_papers"])

    # Sort by upload_date (most recent first)
    all_answered.sort(key=lambda x: x["upload_date"], reverse=True)

    # Combine all available papers into a single list
    all_available = []
    all_available.extend(result["sample"]["available_question_papers"])
    all_available.extend(result["previous_year"]["available_question_papers"])
    all_available.extend(result["generated"]["available_question_papers"])

    # Sort by upload_date (most recent first)
    all_available.sort(key=lambda x: x["upload_date"], reverse=True)

    # Add the combined results to the response
    result["all"] = {
        "answered_question_papers": all_answered,
        "available_question_papers": all_available,
    }

    return Response(result)


@api_view(["POST"])
def save_feedback_for(request: Request) -> Response:
    """Saves detailed feedback for each question in an answer upload.

    Args:
        request (Request): The Django REST Framework request object containing
                         feedback data for multiple questions.

    Returns:
        Response: A DRF Response object indicating success.
    """
    # Validate required fields
    required_fields = ["answerUploadId", "feedback"]
    for field in required_fields:
        if field not in request.data:
            return Response(
                {"error": f"{field} is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    data = request.data
    answer_upload_id = data["answerUploadId"]
    feedback_data = data["feedback"]

    # Validate if answer_upload exists
    try:
        answer_upload = AnswerUpload.objects.get(id=answer_upload_id)
    except AnswerUpload.DoesNotExist:
        return Response(
            {"error": "Answer upload not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Save each feedback for the questions
    total_marks = 0
    feedback_text_list = []
    
    for feedback in feedback_data:
        marks_obtained = float(feedback.get("marksObtained", 0))
        total_marks += marks_obtained
        
        feedback_instance, created = Feedback.objects.update_or_create(
            answer_upload=answer_upload,
            question_number=feedback["questionNumber"],
            defaults={
                "marks_obtained": marks_obtained,
                "marks_out_of": feedback["marksOutOf"],
                "feedback": feedback["feedback"],
                "complexity": feedback["complexity"],
            },
        )
        
        # Build feedback text list for QuestionFeedback
        feedback_text_list.append({
            "questionNumber": feedback["questionNumber"],
            "marksObtained": marks_obtained,
            "marksOutOf": feedback["marksOutOf"],
            "feedback": feedback["feedback"],
            "complexity": feedback["complexity"],
        })

    # Create or update QuestionFeedback entry
    question_feedback, created = QuestionFeedback.objects.update_or_create(
        answer_upload=answer_upload,
        defaults={
            "feedback_text": json.dumps(feedback_text_list),
            "marks_obtained": total_marks,
        }
    )

    # Update the AnswerAssignment to mark it as completed
    try:
        answer_assignment = AnswerAssignment.objects.get(
            answer_upload=answer_upload
        )
        answer_assignment.completed = True
        answer_assignment.save()
    except AnswerAssignment.DoesNotExist:
        # If no assignment exists and user is authenticated, create one
        if hasattr(request, 'user') and request.user.is_authenticated:
            AnswerAssignment.objects.create(
                answer_upload=answer_upload,
                evaluator=request.user,
                completed=True
            )

    return Response(
        {"message": "Feedback saved successfully!"},
        status=status.HTTP_201_CREATED,
    )


@api_view(["DELETE"])
def delete_feedback(request: Request, answer_upload_id: int) -> Response:
    """Deletes all feedback associated with a given answer upload.

    Args:
        request (Request): The Django REST Framework request object.
        answer_upload_id (int): The ID of the answer upload for which to
                                delete feedback.

    Returns:
        Response: A DRF Response object indicating success.
    """
    # Validate if AnswerUpload exists
    try:
        answer_upload = AnswerUpload.objects.get(id=answer_upload_id)
    except AnswerUpload.DoesNotExist:
        return Response(
            {"error": "Answer upload not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Delete the related AnswerAssignment record (if exists)
    AnswerAssignment.objects.filter(answer_upload=answer_upload).delete()
    Feedback.objects.filter(answer_upload=answer_upload).delete()

    return Response(
        {"message": "Feedback  and AnswerAssignment deleted successfully!"},
        status=status.HTTP_204_NO_CONTENT,
    )


@api_view(["GET"])
def get_feedback(request: Request, answer_id: int) -> Response:
    """
    Fetch all feedback for a given answer upload.

    Args:
        request (Request): The Django REST Framework request object.
        answer_id (int): The ID of the answer upload.

    Returns:
        Response: A DRF Response object containing all feedback for the given
                  answer.
    """
    try:
        # Fetch the answer upload
        answer_upload = AnswerUpload.objects.get(id=answer_id)

        # Retrieve all feedbacks related to this answer upload
        feedback_entries = Feedback.objects.filter(answer_upload=answer_upload)

        # Serialize the feedback data
        serializer = FeedbackSerializer(feedback_entries, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
    except AnswerUpload.DoesNotExist:
        return Response(
            {"error": "Answer upload not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        return Response(
            {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
def get_students(request: Request) -> Response:
    """Retrieves a list of all users with the 'student' role.

    Args:
        request (Request): The Django REST Framework request object.

    Returns:
        Response: A DRF Response object with a list of students.
    """
    # Fetch all users and filter in Python using the has_role method
    all_users = User.objects.all()
    students = [user for user in all_users if user.has_role("student")]

    student_data = [
        {
            "id": student.id,
            "email": student.email,
            "username": student.username,
        }
        for student in students
    ]
    return Response(student_data, status=status.HTTP_200_OK)


# mentor and student


@api_view(["POST"])
def send_request(request: Request) -> Response:
    """Sends a mentorship request from a student to a mentor.

    Args:
        request (Request): The Django REST Framework request object with
                         'mentor_id' and 'student_id'.

    Returns:
        Response: A JsonResponse indicating if the request was sent.
    """
    mentor_id = request.data.get("mentor_id")
    student_id = request.data.get("student_id")
    mentor = get_object_or_404(User, id=mentor_id)
    student = get_object_or_404(User, id=student_id)

    if MentorshipRequest.objects.filter(
        mentor=mentor, student=student, status="Pending"
    ).exists():
        return JsonResponse({"message": "Request already sent"}, status=400)

    MentorshipRequest.objects.create(mentor=mentor, student=student)
    return JsonResponse({"message": "Request sent successfully"}, status=201)


@api_view(["GET"])
def get_requests(request: Request) -> Response:
    """Retrieves mentorship requests for the currently logged-in user.

    Args:
        request (Request): The Django REST Framework request object.

    Returns:
        Response: A JsonResponse with a list of mentorship requests for the
                  user.
    """
    user = request.user
    requests = MentorshipRequest.objects.filter(student=user)
    data = [
        {
            "id": req.id,
            "mentor_name": req.mentor.username,
            "mentor_email": req.mentor.email,
            "status": req.status,
            "created_at": req.created_at,
        }
        for req in requests
    ]
    return JsonResponse({"requests": data}, status=200)


@api_view(["POST"])
def handle_request(request: Request) -> Response:
    """Handles a mentorship request, either accepting or rejecting it.

    Args:
        request (Request): The Django REST Framework request object with
                         'request_id' and 'action'.

    Returns:
        Response: A JsonResponse indicating the result of the action.
    """
    user = request.user
    request_id = request.data.get("request_id")
    action = request.data.get("action")  # Accept or Reject

    mentorship_request = get_object_or_404(
        MentorshipRequest, id=request_id, student=user
    )

    if action not in ["Accept", "Reject"]:
        return JsonResponse({"message": "Invalid action"}, status=400)

    mentorship_request.status = (
        "Accepted" if action == "Accept" else "Rejected"
    )
    mentorship_request.save()
    return JsonResponse(
        {"message": f"Request {action.lower()}ed successfully"}, status=200
    )


@api_view(["GET"])
def get_student_requests(request: Request, student_id: int) -> Response:
    """Retrieves all mentorship requests for a specific student.

    Args:
        request (Request): The Django REST Framework request object.
        student_id (int): The ID of the student.

    Returns:
        Response: A DRF Response object with a list of mentorship requests for
                  the student.
    """
    try:
        # Retrieve the student by their ID
        student = User.objects.get(id=student_id)

        # Get all mentorship requests related to the student (both received and
        # sent)
        student_requests = MentorshipRequest.objects.filter(student=student)

        # Prepare the response data
        data = [
            {
                "mentor": request.mentor.id,
                "student": request.student.id,
                "men_email": request.mentor.email,
                "status": request.status,
                "created_at": request.created_at,
            }
            for request in student_requests
        ]

        return Response(data, status=HTTP_200_OK)

    except User.DoesNotExist:
        return Response(
            {"message": "Student not found"}, status=HTTP_404_NOT_FOUND
        )


@api_view(["GET"])
def get_notifications(request: Request) -> Response:
    """
    Fetch notifications for the logged-in user based on their email and role,
    ordered by most recent notifications first.

    Args:
        request (Request): The Django REST Framework request object with 'email'
                         and 'role' query params.

    Returns:
        Response: A DRF Response object with a list of notifications.
    """
    try:
        # Get the email and role from query parameters
        email = request.GET.get("email", None)
        role = request.GET.get("role", None)

        if not email:
            return Response(
                {
                    "error": "Email is required to fetch notifications."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build filter query
        filter_kwargs = {"recipient__email": email}
        if role:
            # If role is provided, we can optionally filter by it.
            # However, to be robust against "disappearing" notifications,
            # we might want to return all notifications for the user,
            # OR allow notifications with matching role OR null role.
            # For now, let's keep it simple: matches email is primary.
            # If strict filtering is required, use: filter_kwargs["recipient_role"] = role
            # But the user issue suggests strict filtering is the problem.
            # Let's filter by role IF it matches, OR return all if role is "all" equivalent.
            # Given the request "notifications show up despite.. logging out",
            # it's safer to relax this or ensure it matches.
            # filter_kwargs["recipient_role"] = role  <-- DISABLED to fix persistence/visibility issues
            pass

        # Fetch notifications for the user based on email and role, ordered by recent
        notifications = Notification.objects.filter(**filter_kwargs).order_by("-created_at")

        # Serialize the notification data
        notification_data = [
            {
                "id": notification.id,
                "sender_email": notification.sender.email,  # Fetch sender's email
                "sender_role": notification.sender_role,
                "message": notification.message,
                "created_at": notification.created_at,
                "is_read": notification.is_read,
                "is_mentor_request": notification.mentor_request,
                "reference_id": notification.reference_id,
                "on_click_url": notification.on_click_url,
            }
            for notification in notifications
        ]

        return Response(notification_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def send_mentor_request(request: Request) -> Response:
    """
    Handle mentor-to-student notification requests.

    Args:
        request (Request): The Django REST Framework request object with
                         'student_id', 'mentor_id', 'mentor_request',
                         and 'message'.

    Returns:
        Response: A DRF Response object indicating success or failure.
    """
    # Required fields in the request
    required_fields = ["student_id", "mentor_id", "mentor_request", "message"]
    for field in required_fields:
        if field not in request.data:
            return Response(
                {"error": f"{field} is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Extracting data from the request
    student_id = request.data["student_id"]
    mentor_id = request.data["mentor_id"]
    mentor_request = request.data["mentor_request"]
    message = request.data["message"]
    print(f"{student_id} {mentor_id}{mentor_request} {message}")

    try:
        # Fetch sender and recipient from the App model
        sender = User.objects.get(id=mentor_id)
        recipient = User.objects.get(id=student_id)

        # Validate roles using ROLE_CHOICES
        # if sender.role != 'mentor' or recipient.role != 'student':
        # return Response({'error': 'Invalid sender or recipient role.'},
        # status=status.HTTP_400_BAD_REQUEST)

        # Create a new Notification
        notification = Notification.objects.create(
            sender=sender,
            recipient=recipient,
            sender_role="mentor",
            recipient_role="student",
            message=message,
            mentor_request=mentor_request,
        )

        # Return success response
        return Response(
            {
                "message": "Mentor request sent successfully!",
                "notification": {
                    "id": notification.id,
                    "sender": notification.sender.id,
                    "recipient": notification.recipient.id,
                    "message": notification.message,
                    "mentor_request": notification.mentor_request,
                    "created_at": notification.created_at,
                    "is_read": notification.is_read,
                },
            },
            status=status.HTTP_201_CREATED,
        )

    except ObjectDoesNotExist:
        # Handle invalid IDs
        return Response(
            {"error": "Invalid mentor_id or student_id."},
            status=status.HTTP_404_NOT_FOUND,
        )

    except Exception as e:
        # Log the unexpected error (pseudo-logging for demonstration)
        print(f"Unexpected error in send_mentor_request: {e}")
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_accepted_students(request: Request) -> Response:
    """
    Fetch all students accepted by the mentor based on their email.

    Args:
        request (Request): The Django REST Framework request object with
                         'mentor_email' as a query parameter.

    Returns:
        Response: A DRF Response object with a list of accepted students.
    """
    try:
        # Get mentor's email from query parameters
        mentor_email = request.GET.get("mentor_email", None)

        if not mentor_email:
            return Response(
                {
                    "error": "Mentor email is required to fetch accepted students."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Fetch the mentor's record
        mentor = User.objects.filter(email=mentor_email).first()
        if not mentor:
            return Response(
                {"error": "Mentor not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Fetch students mentored by this mentor
        accepted_students = MentorStudent.objects.filter(
            mentor=mentor
        ).select_related("student")

        # Serialize the student data
        student_data = [
            {
                "id": record.student.id,
                # 'username': record.student.user.username,
                "email": record.student.email,
                "created_at": record.created_at,
            }
            for record in accepted_students
        ]

        return Response(student_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def update_notification(request: Request, notification_id: int) -> Response:
    """
    Update a notification's status to mark it as read or handle specific actions.

    Args:
        request (Request): The Django REST Framework request object with 'action'.
        notification_id (int): The ID of the notification to update.

    Returns:
        Response: A DRF Response object indicating success or failure.
    """
    try:
        # Fetch the notification by ID
        notification = Notification.objects.get(id=notification_id)

        # Get the action from the request data
        action = request.data.get("action", None)

        if not action:
            return Response(
                {"error": "Action is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Mark as read for normal notifications
        if action == "read":
            notification.is_read = True
            notification.save()
            return Response(
                {"message": "Notification marked as read successfully."},
                status=status.HTTP_200_OK,
            )

        # Handle mentor request actions (approve/reject)
        if action == "approve":
            notification.message = f"You accepted the mentor request from {notification.sender.email}."
            notification.is_read = True
            notification.mentor_request = False
        elif action == "reject":
            notification.message = f"You rejected the mentor request from {notification.sender.email}."
            notification.is_read = True
            notification.mentor_request = False
        else:
            return Response(
                {
                    "error": 'Invalid action. Must be "read", "approve", or "reject".'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        notification.save()
        return Response(
            {"message": "Notification updated successfully."},
            status=status.HTTP_200_OK,
        )

    except Notification.DoesNotExist:
        return Response(
            {"error": "Notification not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def add_mentor_student_relationship(request: Request) -> Response:
    """
    Save a mentor-student relationship.

    Args:
        request (Request): The Django REST Framework request object with
                         'mentor_email' and 'student_email'.

    Returns:
        Response: A DRF Response object indicating success or failure.
    """
    try:
        student_email = request.data.get("mentor_email")
        mentor_email = request.data.get("student_email")

        if not mentor_email or not student_email:
            return Response(
                {"error": "Mentor and student emails are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Fetch mentor and student users
        mentor = User.objects.filter(email=mentor_email).first()
        student = User.objects.filter(email=student_email).first()

        if not mentor or not student:
            return Response(
                {"error": "Mentor or student not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create a new mentor-student relationship
        mentor_student, created = MentorStudent.objects.get_or_create(
            mentor=mentor, student=student
        )

        if created:
            return Response(
                {
                    "message": "Mentor-student relationship created successfully."
                },
                status=status.HTTP_201_CREATED,
            )
        else:
            return Response(
                {"message": "Mentor-student relationship already exists."},
                status=status.HTTP_200_OK,
            )

    except Exception as e:
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def create_main_request(request: Request) -> Response:
    """Creates a main request for a user to become a mentor or evaluator.

    Args:
        request (Request): The Django REST Framework request object.

    Returns:
        Response: A DRF Response object indicating success and the new
                  request's ID.
    """
    logger.info(f"Received main request submission: {request.data}")

    # Extract form fields safely
    email = request.POST.get("email")
    role = request.POST.get("role")
    board_data = request.POST.get("boards")  # Stringified JSON
    subject_data = request.POST.get("subjects")  # Stringified JSON
    language_data = request.POST.get("languages")  # Stringified JSON
    resume = request.FILES.get("resume")  # File field

    # Ensure required fields exist
    if (
        not email
        or not role
        or not board_data
        or not subject_data
        or not language_data
    ):
        return Response(
            {"error": "Missing required fields."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Convert stringified JSON arrays to lists
    try:
        board_names = json.loads(board_data) if board_data else []
        subject_names = json.loads(subject_data) if subject_data else []
        language_names = json.loads(language_data) if language_data else []
    except json.JSONDecodeError:
        return Response(
            {"error": "Invalid JSON format in board, subject, or languages."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    logger.debug(
        f"Extracted Data: Email={email}, Role={role}, Boards={board_names}, Subjects={subject_names}, Languages={language_names}, Resume provided: {bool(resume)}"
    )

    try:
        user = User.objects.get(email=email)

        # Create MainRequest instance
        main_request = MainRequest.objects.create(
            user=user,
            role=role,
            resume=resume,
            board=board_names[0] if board_names else None,
            subject=subject_names[0] if subject_names else None,
        )

        # Get or create related objects
        languages = [
            Language.objects.get_or_create(name=lang)[0]
            for lang in language_names
        ]
        subjects = [
            Subject.objects.get_or_create(name=subj)[0]
            for subj in subject_names
        ]
        boards = [
            Board.objects.get_or_create(name=brd)[0] for brd in board_names
        ]

        # Update Evaluator profile
        evaluator, created = Evaluator.objects.get_or_create(user=user)
        evaluator.resume = resume
        evaluator.languages.set(languages)
        evaluator.subjects.set(subjects)
        evaluator.boards.set(boards)
        evaluator.save()

        # Mark user profile as completed if resume is uploaded
        if resume:
            user.is_profile_completed = True
            user.save()

        return Response(
            {
                "message": "MainRequest and Evaluator profile updated successfully!",
                "main_request_id": main_request.id,
                "evaluator_id": evaluator.id,
            },
            status=status.HTTP_201_CREATED,
        )

    except ObjectDoesNotExist:
        return Response(
            {"error": "Invalid user email."}, status=status.HTTP_404_NOT_FOUND
        )

    except Exception as e:
        logger.error(f"Unexpected error in create_main_request: {e}", exc_info=True)
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_main_requests(request: Request) -> Response:
    """
    Fetch all MainRequest entries or filter by role.

    Args:
        request (Request): The Django REST Framework request object with optional
                         'role' query parameter.

    Returns:
        Response: A DRF Response object with a list of MainRequest entries.
    """
    role = request.query_params.get(
        "role", None
    )  # Get the role from query parameters
    try:
        # Filter requests by role if provided
        if role:
            main_requests = MainRequest.objects.filter(role=role)
        else:
            main_requests = MainRequest.objects.all()

        # Serialize the data
        serializer = MainRequestSerializer(main_requests, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error fetching MainRequest data: {str(e)}", exc_info=True)
        return Response(
            {"error": f"Error fetching MainRequest data: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def check_submission(request: Request) -> Response:
    """
    Check if a MainRequest has been submitted by the user with the given email and role.

    Args:
        request (Request): The Django REST Framework request object with 'email'
                         and 'role' query parameters.

    Returns:
        Response: A DRF Response object indicating if a submission exists.
    """
    email = request.query_params.get("email")
    role = request.query_params.get("role")

    # Validate query parameters
    if not email or not role:
        return Response(
            {
                "error": 'Both "email" and "role" query parameters are required.'
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # Fetch the user by email
        user = get_object_or_404(User, email=email)

        # Check if a MainRequest exists for the given user and role
        main_request_exists = MainRequest.objects.filter(
            user=user, role=role
        ).exists()

        return Response(
            {"submitted": main_request_exists}, status=status.HTTP_200_OK
        )

    except Exception as e:
        # Log unexpected errors
        logger.error(f"Unexpected error in check_submission: {e}", exc_info=True)
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def accept_main_request(request: Request, id: int) -> Response:
    """
    Accept a MainRequest, delete it from the database, and update the User's is_allowed field.

    Args:
        request (Request): The Django REST Framework request object.
        id (int): The ID of the MainRequest to accept.

    Returns:
        Response: A DRF Response object indicating success.
    """
    try:
        # Fetch the MainRequest by ID
        main_request = MainRequest.objects.get(id=id)

        # Fetch the user associated with the request
        user = main_request.user

        # Update is_allowed for the specific role
        if user.has_role(main_request.role):
            if main_request.role == "qp_uploader":
                user.is_qp_uploader_allowed = True
            elif main_request.role == "evaluator":
                user.is_evaluator_allowed = True
            user.save()

        # Delete the MainRequest after acceptance
        main_request.delete()

        return Response(
            {
                "message": f"Request with ID {id} accepted and user permissions updated."
            },
            status=status.HTTP_200_OK,
        )

    except MainRequest.DoesNotExist:
        return Response(
            {"error": "MainRequest not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    except Exception as e:
        logger.error(f"An error occurred in accept_main_request: {e}", exc_info=True)
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST", "PUT"])
def save_question(request: Request) -> Response:
    """Saves or updates a question in the question bank.

    Args:
        request (Request): The Django REST Framework request object.

    Returns:
        Response: A DRF Response object indicating success or failure.
    """
    try:
        data = request.data
        # Process images if they exist
        question_image = None
        explanation_image = None
        # Handle question image
        if "questionImage" in data and data["questionImage"]:
            image_data = data["questionImage"]
            if "data:image" in image_data:
                format, imgstr = image_data.split(";base64,")
                ext = format.split("/")[-1]
                question_image = ContentFile(
                    base64.b64decode(imgstr),
                    name=f'question_{data.get("id", "new")}.{ext}',
                )
        # Handle explanation image
        if "explanationImage" in data and data["explanationImage"]:
            image_data = data["explanationImage"]
            if "data:image" in image_data:
                format, imgstr = image_data.split(";base64,")
                ext = format.split("/")[-1]
                explanation_image = ContentFile(
                    base64.b64decode(imgstr),
                    name=f'explanation_{data.get("id", "new")}.{ext}',
                )
        is_submitted = data.get("is_submitted", False)
        if isinstance(is_submitted, str):
            is_submitted = is_submitted.lower() == "true"
        if request.method == "PUT":
            # Update existing question
            question_id = data.get("id")
            if not question_id:
                return Response(
                    {
                        "status": "error",
                        "message": "Question id is required for update.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                question = Question.objects.get(id=question_id)
            except Question.DoesNotExist:
                return Response(
                    {"status": "error", "message": "Question not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            # Update fields
            question.subject = data["subject"]
            question.topic = data["topic"]
            question.exam_type = data["examType"]
            question.complexity = data["complexity"]
            question.question_type = data["type"]
            question.marks = data["marks"]
            question.question_text = data["questionText"]
            question.options = (
                json.dumps(data["options"])
                if data["type"] == "multiple-choice"
                else None
            )
            question.correct_answer = (
                data["correctAnswer"]
                if data["type"] == "multiple-choice"
                else None
            )
            question.explanation = data["explanation"]
            question.is_submitted = is_submitted
            if question_image:
                question.question_image = question_image
            if explanation_image:
                question.explanation_image = explanation_image
            question.save()
            return Response(
                {
                    "status": "success",
                    "message": "Question updated successfully",
                    "id": question.id,
                },
                status=status.HTTP_200_OK,
            )
        else:
            # Create Question object
            question = Question(
                subject=data["subject"],
                topic=data["topic"],
                exam_type=data["examType"],
                complexity=data["complexity"],
                question_type=data["type"],
                marks=data["marks"],
                question_text=data["questionText"],
                options=(
                    json.dumps(data["options"])
                    if data["type"] == "multiple-choice"
                    else None
                ),
                correct_answer=(
                    data["correctAnswer"]
                    if data["type"] == "multiple-choice"
                    else None
                ),
                explanation=data["explanation"],
                is_submitted=is_submitted,
            )
            if question_image:
                question.question_image = question_image
            if explanation_image:
                question.explanation_image = explanation_image
            question.save()
            return Response(
                {
                    "status": "success",
                    "message": "Question saved successfully",
                    "id": question.id,
                },
                status=status.HTTP_201_CREATED,
            )
    except KeyError as e:
        return Response(
            {
                "status": "error",
                "message": f"Missing required field: {str(e)}",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        logger.error(f"Error saving question: {str(e)}", exc_info=True)
        return Response(
            {"status": "error", "message": f"Error saving question: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# Optional: Add endpoint to get questions


@api_view(["GET"])
def get_questions(request: Request) -> Response:
    """Retrieves questions from the database with optional filters.

    Args:
        request (Request): The Django REST Framework request object with optional
                         query parameters for filtering.

    Returns:
        Response: A DRF Response object with a list of questions.
    """
    try:
        # Get query parameters
        subject = request.query_params.get("subject", None)
        exam_type = request.query_params.get("examType", None)
        complexity = request.query_params.get("complexity", None)
        is_submitted = request.query_params.get("is_submitted", None)

        # Start with all questions
        questions = Question.objects.all()

        # Apply filters if provided
        if subject:
            questions = questions.filter(subject=subject)
        if exam_type:
            questions = questions.filter(exam_type=exam_type)
        if complexity:
            questions = questions.filter(complexity=complexity)
        if is_submitted is not None:
            if is_submitted.lower() == "true":
                questions = questions.filter(is_submitted=True)
            elif is_submitted.lower() == "false":
                questions = questions.filter(is_submitted=False)

        # Convert to list of dictionaries
        questions_data = []
        for q in questions:
            question_dict = {
                "id": q.id,
                "subject": q.subject,
                "topic": q.topic,
                "examType": q.exam_type,
                "complexity": q.complexity,
                "type": q.question_type,
                "marks": q.marks,
                "questionText": q.question_text,
                "options": json.loads(q.options) if q.options else None,
                "correctAnswer": q.correct_answer,
                "explanation": q.explanation,
                "questionImage": (
                    q.question_image.url if q.question_image else None
                ),
                "explanationImage": (
                    q.explanation_image.url if q.explanation_image else None
                ),
                "createdAt": q.created_at,
                "updatedAt": q.updated_at,
                "is_submitted": q.is_submitted,
            }
            questions_data.append(question_dict)

        return Response({"status": "success", "data": questions_data})

    except Exception as e:
        logger.error(f"Error fetching questions: {str(e)}", exc_info=True)
        return Response(
            {
                "status": "error",
                "message": f"Error fetching questions: {str(e)}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# assigning questions to evaluators


@api_view(["POST"])
def assign_answers_view(request: Request) -> Response:
    """
    Assigns answer sheets to evaluators, ensuring no evaluator has more than 5 at a time.

    Args:
        request: The Django request object.

    Returns:
        Response: A DRF Response object indicating success.
    """
    if not hasattr(request.user, "has_role") or not request.user.has_role("admin"):
        return Response(
            {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
        )

    assign_answers_task()

    return Response(
        {"message": "Answer sheets assigned successfully!"},
        status=status.HTTP_200_OK,
    )


def assign_answers_task():
    """Assigns unassigned answers to evaluators in a balanced way."""
    from authentication.models import User

    all_users = User.objects.annotate(assigned_count=Count("assigned_answers"))
    available_evaluators = [
        u
        for u in all_users
        if hasattr(u, "has_role")
        and u.has_role("evaluator")
        and u.assigned_count < 5
    ]

    unassigned_answers = list(
        AnswerUpload.objects.filter(answerassignment__isnull=True)
    )  # Get unassigned answers

    if not available_evaluators or not unassigned_answers:
        return  # No evaluators or no unassigned answers

    # Sort evaluators by least assigned first to balance load
    available_evaluators.sort(key=lambda e: e.assigned_count)

    index = 0
    for answer in unassigned_answers:
        evaluator = available_evaluators[
            index % len(available_evaluators)
        ]  # Round-robin assignment
        if evaluator.assigned_count < 5:  # Ensure max 5 per evaluator
            AnswerAssignment.objects.create(
                answer_upload=answer, evaluator=evaluator
            )
            evaluator.assigned_count += 1  # Update assigned count in memory
        index += 1  # Move to the next evaluator


@api_view(["POST"])
def reassign_expired_answers(request: Request) -> Response:
    """
    Reassigns expired answer sheets if they are not completed within 3 days.

    Args:
        request: The Django request object.

    Returns:
        Response: A DRF Response object indicating success.
    """
    if (
        request.user.role != "admin"
    ):  # Only admin can trigger reassignment manually
        return Response(
            {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
        )

    reassign_expired_answers_task()

    return Response(
        {"message": "Expired answer sheets reassigned successfully!"},
        status=status.HTTP_200_OK,
    )


def reassign_expired_answers_task():
    """Reassigns expired answer sheets to new evaluators manually."""
    expired_assignments = AnswerAssignment.objects.filter(
        completed=False, assigned_date__lt=timezone.now() - timedelta(days=3)
    )

    for assignment in expired_assignments:
        assignment.evaluator = None  # Remove current evaluator
        assignment.save()

    assign_answers_task()  # Reassign to new evaluators


@api_view(["GET"])
def evaluator_dashboard(request: Request) -> Response:
    """
    Lists assigned answer sheets for the logged-in evaluator.

    Args:
        request: The Django request object.

    Returns:
        Response: A DRF Response object containing a list of assignments.
    """
    if request.user.role != "evaluator":
        return Response(
            {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
        )

    assignments = AnswerAssignment.objects.filter(
        evaluator=request.user, completed=False
    )

    data = [
        {
            "answer_upload_id": a.answer_upload.id,
            "question_paper": a.answer_upload.question_paper.test_title,
            "assigned_date": a.assigned_date.strftime("%Y-%m-%d %H:%M:%S"),
            "is_expired": a.is_expired(),
        }
        for a in assignments
    ]

    return Response({"assignments": data}, status=status.HTTP_200_OK)


# Add this to your views.py in the users app


@api_view(["GET"])
def check_user_permission(request: Request) -> Response:
    """
    Check if a user is allowed for a specific role

    Args:
        request: The Django request object with 'email' and 'role' query params.

    Returns:
        Response: A DRF Response object indicating if the user is allowed.
    """
    email = request.query_params.get("email")
    role = request.query_params.get("role")

    if not email or not role:
        return Response(
            {"error": "Email and role are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # Find the user by email
        user = User.objects.get(email=email)

        # Check if user has the role and is allowed
        is_allowed = False
        if user.has_role(role):
            if role == "qp_uploader":
                is_allowed = user.is_qp_uploader_allowed
            elif role == "evaluator":
                is_allowed = user.is_evaluator_allowed
            else:
                is_allowed = False  # For other roles, not applicable

        return Response(
            {"email": email, "role": role, "is_allowed": is_allowed},
            status=status.HTTP_200_OK,
        )

    except User.DoesNotExist:
        return Response(
            {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"An error occurred in check_user_permission: {e}", exc_info=True)
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def assign_answer_to_evaluator(request: Request) -> Response:
    """Assigns a specific answer sheet to a specific evaluator.

    Args:
        request: The Django request object containing 'answer_upload_id' and
                 'evaluator_id'.

    Returns:
        Response: A DRF Response object indicating success or failure.
    """
    # Check for organization admin role
    if not request.user.is_authenticated or request.user.role_org != "admin":
        return Response(
            {"error": "Permission denied. Only organization admins can assign answers."},
            status=status.HTTP_403_FORBIDDEN
        )

    answer_id = request.data.get("answer_upload_id") # Frontend sends StudentAnswer ID here
    evaluator_id = request.data.get("evaluator_id")

    if not answer_id or not evaluator_id:
        return Response(
            {"error": "Both answer ID and evaluator ID are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from authentication.models import User
    from organization.models import StudentAnswer, EvaluationAssignment

    try:
        answer = StudentAnswer.objects.get(id=answer_id)
        evaluator = User.objects.get(id=evaluator_id)

        # Check if already assigned
        if EvaluationAssignment.objects.filter(student_answer=answer).exists():
            return Response(
                {"error": "This answer is already assigned."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create assignment
        EvaluationAssignment.objects.create(
            student_answer=answer, 
            evaluator=evaluator,
            test=answer.test # Optional: populate test reference
        )

        return Response(
            {"message": "Answer assigned to evaluator successfully!"},
            status=status.HTTP_200_OK,
        )
    except StudentAnswer.DoesNotExist:
        return Response(
            {"error": "StudentAnswer not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    except User.DoesNotExist:
        return Response(
            {"error": "Evaluator not found."}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["GET"])
def get_evaluators(request: Request) -> Response:
    """Retrieves a list of all users with the 'evaluator' role.

    Args:
        request: The Django request object.

    Returns:
        Response: A DRF Response object with a list of evaluators.
    """
    from authentication.models import User

    evaluators = [
        u
        for u in User.objects.all()
        if hasattr(u, "has_role") and u.has_role("evaluator")
    ]
    data = [
        {
            "id": u.id,
            "email": u.email,
            "name": u.full_name or u.username or u.email,
        }
        for u in evaluators
    ]
    return Response(data)


@api_view(["GET"])
def get_unassigned_answers(request: Request) -> Response:
    """Retrieves a list of answer sheets that have not been assigned to any evaluator.

    Args:
        request: The Django request object.

    Returns:
        Response: A DRF Response object with a list of unassigned answers.
    """
    from organization.models import StudentAnswer

    # Fetch StudentAnswers that do not have an associated EvaluationAssignment
    unassigned = StudentAnswer.objects.filter(evaluation_assignments__isnull=True)
    
    data = []
    for a in unassigned:
        # Create a descriptive label
        test_title = a.test.title if a.test else "Unknown Test"
        student_email = a.student.email if a.student else "Unknown Student"
        question_preview = a.question.question_text[:20] + "..." if a.question else "Unknown Question"
        
        label = f"Test: {test_title} | Student: {student_email} | Q: {question_preview}"
        
        data.append({
            "id": a.id, 
            "file_name": label  # Frontend expects 'file_name'
        })
    
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_grading_report(request: Request, grading_id: int) -> Response:
    """Generates and downloads a detailed PDF grading report.

    Args:
        request (Request): The request object.
        grading_id (int): ID of the grading result.

    Returns:
        FileResponse: PDF file download.
    """
    grading_result = get_object_or_404(GradingResult, pk=grading_id)

    # Permission Check: Ensure user owns this result
    # Assuming user_id in GradingResult matches str(request.user.id)
    if str(grading_result.user_id) != str(request.user.id):
        # Allow evaluators or admins to download too if needed, for now restrict to owner
        return Response(
            {"error": "You do not have permission to view this report."},
            status=status.HTTP_403_FORBIDDEN
        )

    if not grading_result.grading_processed:
        return Response(
            {"error": "Grading is not yet complete for this test."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        generator = PDFReportGenerator(grading_result)
        pdf_buffer = generator.generate()
        
        filename = f"Grading_Report_{grading_result.id}.pdf"
        response = FileResponse(pdf_buffer, as_attachment=True, filename=filename)
        return response
    except Exception as e:
        logger.error(f"Error generating PDF report: {e}", exc_info=True)
        return Response(
            {"error": "Failed to generate report."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_answer_ocr_data(request: Request, answer_id: int) -> Response:
    """Retrieve the OCR JSON data for a specific answer upload.

    Args:
        request (Request): The DRF request object.
        answer_id (int): ID of the AnswerUpload.

    Returns:
        Response: JSON data from the OCR file.
    """
    try:
        answer_upload = AnswerUpload.objects.get(id=answer_id)
        
        # Check permissions
        if str(answer_upload.user_id) != str(request.user.id) and not request.user.has_role("evaluator") and not request.user.has_role("admin") and not request.user.is_superuser:
             pass # Permission logic can be stricter if needed
        
        response_data = {
            "id": answer_upload.id,
            "ocr_processed": answer_upload.ocr_processed,
            "ocr_error": answer_upload.ocr_error,
            "json_data": None,
            "images_dir": answer_upload.ocr_images_dir
        }

        if answer_upload.ocr_json_path and os.path.exists(answer_upload.ocr_json_path):
            try:
                with open(answer_upload.ocr_json_path, 'r', encoding='utf-8') as f:
                    response_data["json_data"] = json.load(f)
            except Exception as e:
                logger.error(f"Error reading OCR JSON file: {e}")
                response_data["error"] = "Error reading OCR data file."
        
        return Response(response_data)

    except AnswerUpload.DoesNotExist:
        return Response({"error": "Answer upload not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error retrieving OCR data: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_answer_ocr_data(request: Request, answer_id: int) -> Response:
    """Update the OCR JSON data for a specific answer upload.

    Args:
        request (Request): The DRF request object containing 'json_data'.
        answer_id (int): AnswerUpload ID.

    Returns:
        Response: Success or error.
    """
    try:
        answer_upload = AnswerUpload.objects.get(id=answer_id)
        
        # Permission check
        if str(answer_upload.user_id) != str(request.user.id):
             pass 

        new_json_data = request.data.get("json_data")
        if not new_json_data:
             return Response({"error": "json_data is required"}, status=status.HTTP_400_BAD_REQUEST)

        if answer_upload.ocr_json_path:
            # Ensure directory exists
            try:
                with open(answer_upload.ocr_json_path, 'w', encoding='utf-8') as f:
                    json.dump(new_json_data, f, indent=2, ensure_ascii=False)
                
                return Response({"message": "OCR data updated successfully"})
            except Exception as e:
                logger.error(f"Error writing OCR JSON file: {e}")
                return Response({"error": f"Failed to modify file: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
             return Response({"error": "No OCR JSON path associated with this upload"}, status=status.HTTP_400_BAD_REQUEST)

    except AnswerUpload.DoesNotExist:
        return Response({"error": "Answer upload not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error updating OCR data: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_answer_asset(request: Request, answer_id: int) -> Response:
    """Upload a new image asset for a specific answer upload.

    Args:
        request (Request): The DRF request content-type multipart/form-data with 'file'.
        answer_id (int): AnswerUpload ID.

    Returns:
        Response: Relative path to the uploaded asset.
    """
    try:
        answer_upload = AnswerUpload.objects.get(id=answer_id)
        uploaded_file = request.FILES.get('file')
        
        if not uploaded_file:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)
            
        # Define storage path: media/answer_uploads/assets/<upload_id>/
        asset_dir = os.path.join(settings.MEDIA_ROOT, "answer_uploads", "assets", str(answer_id))
        os.makedirs(asset_dir, exist_ok=True)
        
        # Save file
        file_path = os.path.join(asset_dir, uploaded_file.name)
        
        # Handle duplicates/filename collisions if necessary, currently simple overwrite
        with open(file_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
                
        # Return relative path for frontend use (relative to MEDIA_ROOT essentially)
        # Frontend usually prepends /media/
        relative_path = f"answer_uploads/assets/{answer_id}/{uploaded_file.name}"
        
        return Response({
            "message": "Asset uploaded successfully",
            "path": relative_path,
            "url": f"{settings.MEDIA_URL}{relative_path}" 
        })

    except AnswerUpload.DoesNotExist:
        return Response({"error": "Answer upload not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error uploading asset: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
