import pytest
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch
from grade.tasks import assign_answers_task, reassign_expired_answers_task, assign_single_answer_task
from grade.models import AnswerUpload, AnswerAssignment
from authentication.models import User, Organization
from django.core.files.uploadedfile import SimpleUploadedFile

@pytest.fixture
def org(db):
    """Fixture for a test Organization."""
    return Organization.objects.create(name="Test Org")

@pytest.fixture
def evaluator1(db):
    """Fixture for the first test evaluator."""
    return User.objects.create(username="evaluator1", email="eval1@example.com", is_evaluator=True, active_role="evaluator")

@pytest.fixture
def evaluator2(db):
    """Fixture for the second test evaluator."""
    return User.objects.create(username="evaluator2", email="eval2@example.com", is_evaluator=True, active_role="evaluator")

@pytest.fixture
def student(db):
    """Fixture for a test student."""
    return User.objects.create(username="student", email="student@example.com", is_student=True, active_role="student")

@pytest.fixture
def answer1(db, student, org):
    """Fixture for the first test answer upload."""
    file = SimpleUploadedFile("test1.pdf", b"file_content_1")
    return AnswerUpload.objects.create(
        file=file, user_id=student.id, organization=org, question_paper_type="sample", question_paper_id=1
    )

@pytest.fixture
def answer2(db, student, org):
    """Fixture for the second test answer upload."""
    file = SimpleUploadedFile("test2.pdf", b"file_content_2")
    return AnswerUpload.objects.create(
        file=file, user_id=student.id, organization=org, question_paper_type="sample", question_paper_id=2
    )

@patch('grade.tasks.logger')
def test_assign_answers_task_success(mock_logger, db, answer1, answer2, evaluator1, evaluator2):
    """Test successful assignment of answers to evaluators."""
    assign_answers_task()
    assignments = AnswerAssignment.objects.all()
    assert assignments.count() == 2
    assigned_evaluators = [assignment.evaluator for assignment in assignments]
    assert evaluator1 in assigned_evaluators
    assert evaluator2 in assigned_evaluators
    mock_logger.info.assert_called_with("assign_answers_task completed successfully.")

@patch('grade.tasks.logger')
def test_assign_answers_task_no_evaluators(mock_logger, db, answer1, answer2, evaluator1, evaluator2):
    """Test assign_answers_task when no evaluators are available."""
    # Convert evaluators to students
    evaluator1.is_evaluator = False
    evaluator1.is_student = True
    evaluator1.active_role = "student"
    evaluator1.save()
    evaluator2.is_evaluator = False
    evaluator2.is_student = True
    evaluator2.active_role = "student"
    evaluator2.save()
    assign_answers_task()
    assignments = AnswerAssignment.objects.all()
    assert assignments.count() == 0

@patch('grade.tasks.logger')
def test_assign_answers_task_no_unassigned_answers(mock_logger, db, answer1, answer2, evaluator1, evaluator2):
    """Test assign_answers_task when no unassigned answers exist."""
    AnswerAssignment.objects.create(answer_upload=answer1, evaluator=evaluator1)
    AnswerAssignment.objects.create(answer_upload=answer2, evaluator=evaluator2)
    assign_answers_task()
    assignments = AnswerAssignment.objects.all()
    assert assignments.count() == 2

@patch('grade.tasks.logger')
def test_reassign_expired_answers_task(mock_logger, db, answer1, answer2, evaluator1, evaluator2):
    """Test reassignment of expired answer assignments."""
    expired_assignment = AnswerAssignment.objects.create(
        answer_upload=answer1,
        evaluator=evaluator1,
        assigned_date=timezone.now() - timedelta(days=4),
        completed=False
    )
    valid_assignment = AnswerAssignment.objects.create(
        answer_upload=answer2,
        evaluator=evaluator2,
        assigned_date=timezone.now() - timedelta(days=1),
        completed=False
    )
    reassign_expired_answers_task()
    expired_assignment.refresh_from_db()
    assert expired_assignment.evaluator is not None
    assert expired_assignment.evaluator in [evaluator1, evaluator2]
    valid_assignment.refresh_from_db()
    assert valid_assignment.evaluator == evaluator2
    mock_logger.info.assert_called_with("reassign_expired_answers_task completed successfully.")

@patch('grade.tasks.logger')
def test_assign_single_answer_task_success(mock_logger, db, answer1, evaluator1):
    """Test successful assignment of a single answer."""
    assign_single_answer_task(answer1.id)
    assignment = AnswerAssignment.objects.get(answer_upload=answer1)
    assert assignment.evaluator == evaluator1
    mock_logger.info.assert_called_with(f"assign_single_answer_task for answer_id {answer1.id} completed successfully.")

@patch('grade.tasks.logger')
def test_assign_single_answer_task_answer_not_found(mock_logger, db):
    """Test assign_single_answer_task with non-existent answer ID."""
    assign_single_answer_task(99999)
    assignments = AnswerAssignment.objects.all()
    assert assignments.count() == 0
    mock_logger.error.assert_called_with("AnswerUpload with id 99999 does not exist.")

@patch('grade.tasks.logger')
def test_assign_single_answer_task_already_assigned(mock_logger, db, answer1, evaluator1):
    """Test assign_single_answer_task when answer is already assigned."""
    AnswerAssignment.objects.create(answer_upload=answer1, evaluator=evaluator1)
    assign_single_answer_task(answer1.id)
    assignments = AnswerAssignment.objects.filter(answer_upload=answer1)
    assert assignments.count() == 1

@patch('grade.tasks.logger')
def test_assign_single_answer_task_no_evaluators(mock_logger, db, answer1, evaluator1, evaluator2):
    """Test assign_single_answer_task when no evaluators are available."""
    evaluator1.is_evaluator = False
    evaluator1.is_student = True
    evaluator1.active_role = "student"
    evaluator1.save()
    evaluator2.is_evaluator = False
    evaluator2.is_student = True
    evaluator2.active_role = "student"
    evaluator2.save()
    assign_single_answer_task(answer1.id)
    assignments = AnswerAssignment.objects.all()
    assert assignments.count() == 0

@patch('grade.tasks.logger')
def test_assign_answers_task_evaluator_limit(mock_logger, db, student, org, evaluator1, evaluator2):
    """Test that evaluators don't get more than 5 assignments."""
    file = SimpleUploadedFile("test.pdf", b"file_content")
    for i in range(10):
        AnswerUpload.objects.create(
            file=file,
            user_id=student.id,
            organization=org,
            question_paper_type="sample",
            question_paper_id=i + 3,
        )
    assign_answers_task()
    evaluator1_assignments = AnswerAssignment.objects.filter(evaluator=evaluator1).count()
    evaluator2_assignments = AnswerAssignment.objects.filter(evaluator=evaluator2).count()
    assert evaluator1_assignments <= 5
    assert evaluator2_assignments <= 5
