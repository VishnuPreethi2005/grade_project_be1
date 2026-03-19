"""
Celery and background tasks for the grade app.

Defines asynchronous tasks for OCR processing, grading, and related workflows.
"""
# myapp/tasks.py

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import AnswerAssignment, AnswerUpload
from django.db.models import Count
from authentication.models import User
import logging

logger = logging.getLogger(__name__)


@shared_task
def assign_answers_task():
    """
    Assigns unassigned answers to available evaluators, ensuring no evaluator has more than 5 assignments.

    Returns:
        None
    """
    logger.info("Starting assign_answers_task.")
    try:
        all_users = User.objects.annotate(assigned_count=Count("assigned_answers"))
        available_evaluators = [
            u
            for u in all_users
            if u.has_role("evaluator") and u.assigned_count < 5
        ]
        unassigned_answers = list(
            AnswerUpload.objects.filter(answerassignment__isnull=True)
        )
        if not available_evaluators or not unassigned_answers:
            return
        available_evaluators.sort(key=lambda e: e.assigned_count)
        index = 0
        for answer in unassigned_answers:
            evaluator = available_evaluators[index % len(available_evaluators)]
            if evaluator.assigned_count < 5:
                AnswerAssignment.objects.create(
                    answer_upload=answer, evaluator=evaluator
                )
                evaluator.assigned_count += 1  # local increment
            index += 1
        logger.info("assign_answers_task completed successfully.")
    except Exception as e:
        logger.error(f"Error in assign_answers_task: {str(e)}")


@shared_task
def reassign_expired_answers_task():
    """
    Reassigns expired answer sheets (not completed within 3 days) to new evaluators.

    Returns:
        None
    """
    logger.info("Starting reassign_expired_answers_task.")
    try:
        expired_assignments = AnswerAssignment.objects.filter(
            completed=False, assigned_date__lt=timezone.now() - timedelta(days=3)
        )
        for assignment in expired_assignments:
            assignment.evaluator = None
            assignment.save()
        assign_answers_task()
        logger.info("reassign_expired_answers_task completed successfully.")
    except Exception as e:
        logger.error(f"Error in reassign_expired_answers_task: {str(e)}")


@shared_task
def assign_single_answer_task(answer_id: int):
    """
    Assigns a single answer sheet to an available evaluator.

    Args:
        answer_id (int): The ID of the AnswerUpload object to assign.

    Returns:
        None
    """
    logger.info(f"Starting assign_single_answer_task for answer_id {answer_id}.")
    from authentication.models import User
    try:
        try:
            answer = AnswerUpload.objects.get(id=answer_id)
        except AnswerUpload.DoesNotExist:
            logger.error(f"AnswerUpload with id {answer_id} does not exist.")
            return
        if AnswerAssignment.objects.filter(answer_upload=answer).exists():
            return
        all_users = User.objects.annotate(assigned_count=Count("assigned_answers"))
        available_evaluators = [
            u
            for u in all_users
            if u.has_role("evaluator") and u.assigned_count < 5
        ]
        available_evaluators.sort(key=lambda e: e.assigned_count)
        if available_evaluators:
            evaluator = available_evaluators[0]
            AnswerAssignment.objects.create(
                answer_upload=answer, evaluator=evaluator
            )
        logger.info(f"assign_single_answer_task for answer_id {answer_id} completed successfully.")
    except Exception as e:
        logger.error(f"Error in assign_single_answer_task for answer_id {answer_id}: {str(e)}")
