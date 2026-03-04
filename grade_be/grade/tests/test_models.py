from django.test import TestCase
from grade.models import (
    GradingResult,
    AnswerUpload,
    Question,
    Feedback,
    MainRequest,
    Questions,
    SampleQuestionPaper,
    PreviousYearQuestionPaper,
    GeneratedQuestionPaper,
    QuestionFeedback,
    AnswerAssignment,
    MentorshipRequest,
    Notification,
    MentorStudent,
    Evaluator,
    Language,
    Subject,
    Board,
)
from authentication.models import User, Organization
from django.core.files.uploadedfile import SimpleUploadedFile


class ModelCreationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            username="testuser", email="test@example.com"
        )
        self.org = Organization.objects.create(name="Test Org")

    def test_answer_upload_creation(self):
        file = SimpleUploadedFile("test.pdf", b"file_content")
        answer_upload = AnswerUpload.objects.create(
            file=file,
            user_id=self.user.id,
            organization=self.org,
            question_paper_type="sample",
            question_paper_id=1,
        )
        self.assertIsInstance(answer_upload, AnswerUpload)
        self.assertEqual(answer_upload.organization, self.org)

    def test_grading_result_creation(self):
        file = SimpleUploadedFile("test.pdf", b"file_content")
        answer_upload = AnswerUpload.objects.create(
            file=file,
            user_id=self.user.id,
            organization=self.org,
            question_paper_type="sample",
            question_paper_id=1,
        )
        grading_result = GradingResult.objects.create(
            answer_upload=answer_upload,
            user_id=str(self.user.id),
            total_score=90,
            max_possible_score=100,
            percentage=90.0,
        )
        self.assertEqual(
            str(grading_result),
            f"Grading for Answer {answer_upload.id} - 90/100",
        )

    def test_question_creation(self):
        question = Question.objects.create(
            subject="Math",
            topic="Algebra",
            exam_type="CBSE",
            complexity="easy",
            question_type="short-answer",
            marks=5,
            question_text="What is 2+2?",
        )
        self.assertEqual(str(question), "Math - Algebra - short-answer")

    def test_feedback_creation(self):
        file = SimpleUploadedFile("test.pdf", b"file_content")
        answer_upload = AnswerUpload.objects.create(
            file=file,
            user_id=self.user.id,
            organization=self.org,
            question_paper_type="sample",
            question_paper_id=1,
        )
        feedback = Feedback.objects.create(
            answer_upload=answer_upload,
            question_number=1,
            marks_obtained=4.5,
            feedback="Good answer",
            complexity="easy",
            marks_out_of=5.0,
        )
        self.assertEqual(str(feedback), "Feedback for Question 1")

    def test_main_request_creation(self):
        file = SimpleUploadedFile("resume.pdf", b"file_content")
        main_request = MainRequest.objects.create(
            user=self.user,
            role="student",
            resume=file,
            board="CBSE",
            subject="Math",
        )
        self.assertIn("MainRequest by", str(main_request))

    def test_questions_creation(self):
        questions = Questions.objects.create(
            organization=self.org,
            updated_by="test@example.com",
            test_title="Test Paper",
            board="CBSE",
            subject="Math",
            questions=[],
            total_marks=100,
            total_questions=20,
            file=SimpleUploadedFile("qp.pdf", b"file_content"),
        )
        self.assertEqual(questions.test_title, "Test Paper")

    def test_sample_question_paper_creation(self):
        sample_qp = SampleQuestionPaper.objects.create(
            organization=self.org,
            updated_by="test@example.com",
            test_title="Sample Paper",
            board="CBSE",
            subject="Math",
            questions=[],
            total_marks=100,
            total_questions=20,
            file=SimpleUploadedFile("sample.pdf", b"file_content"),
        )
        self.assertEqual(sample_qp.test_title, "Sample Paper")

    def test_previous_year_question_paper_creation(self):
        prev_qp = PreviousYearQuestionPaper.objects.create(
            organization=self.org,
            updated_by="test@example.com",
            test_title="Prev Year",
            board="CBSE",
            subject="Math",
            questions=[],
            total_marks=100,
            total_questions=20,
            file=SimpleUploadedFile("prev.pdf", b"file_content"),
            year=2020,
        )
        self.assertEqual(prev_qp.year, 2020)

    def test_generated_question_paper_creation(self):
        gen_qp = GeneratedQuestionPaper.objects.create(
            organization=self.org,
            updated_by="test@example.com",
            test_title="Generated",
            board="CBSE",
            subject="Math",
            questions=[],
            total_marks=100,
            total_questions=20,
            file=SimpleUploadedFile("gen.pdf", b"file_content"),
            user_id=str(self.user.id),
        )
        self.assertEqual(gen_qp.test_title, "Generated")

    def test_question_feedback_creation(self):
        file = SimpleUploadedFile("test.pdf", b"file_content")
        answer_upload = AnswerUpload.objects.create(
            file=file,
            user_id=self.user.id,
            organization=self.org,
            question_paper_type="sample",
            question_paper_id=1,
        )
        feedback = QuestionFeedback.objects.create(
            answer_upload=answer_upload,
            feedback_text="Well done",
            marks_obtained=5,
        )
        self.assertEqual(feedback.marks_obtained, 5)

    def test_answer_assignment_creation(self):
        file = SimpleUploadedFile("test.pdf", b"file_content")
        answer_upload = AnswerUpload.objects.create(
            file=file,
            user_id=self.user.id,
            organization=self.org,
            question_paper_type="sample",
            question_paper_id=1,
        )
        assignment = AnswerAssignment.objects.create(
            answer_upload=answer_upload, evaluator=self.user
        )
        self.assertFalse(assignment.completed)
        self.assertIn(str(self.user), str(assignment))

    def test_mentorship_request_creation(self):
        mentor = User.objects.create(
            username="mentor", email="mentor@example.com"
        )
        student = User.objects.create(
            username="student", email="student@example.com"
        )
        req = MentorshipRequest.objects.create(
            mentor=mentor, student=student, status="Pending"
        )
        self.assertEqual(req.status, "Pending")

    def test_notification_creation(self):
        sender = User.objects.create(
            username="sender", email="sender@example.com"
        )
        recipient = User.objects.create(
            username="recipient", email="recipient@example.com"
        )
        notif = Notification.objects.create(
            sender=sender,
            recipient=recipient,
            sender_role="mentor",
            recipient_role="student",
            message="Test notification",
        )
        self.assertIn("Notification from", str(notif))

    def test_mentor_student_creation(self):
        mentor = User.objects.create(
            username="mentor2", email="mentor2@example.com"
        )
        student = User.objects.create(
            username="student2", email="student2@example.com"
        )
        ms = MentorStudent.objects.create(mentor=mentor, student=student)
        self.assertEqual(ms.mentor, mentor)
        self.assertEqual(ms.student, student)

    def test_evaluator_creation(self):
        evaluator = User.objects.create(
            username="eval", email="eval@example.com"
        )
        lang = Language.objects.create(name="English")
        subj = Subject.objects.create(name="Math")
        board = Board.objects.create(name="CBSE")
        eval_obj = Evaluator.objects.create(user=evaluator, rating=4.5)
        eval_obj.languages.add(lang)
        eval_obj.subjects.add(subj)
        eval_obj.boards.add(board)
        self.assertEqual(eval_obj.rating, 4.5)
        self.assertIn(lang, eval_obj.languages.all())

    def test_language_subject_board_creation(self):
        lang = Language.objects.create(name="Hindi")
        subj = Subject.objects.create(name="Science")
        board = Board.objects.create(name="ICSE")
        self.assertEqual(str(lang), "Hindi")
        self.assertEqual(str(subj), "Science")
        self.assertEqual(str(board), "ICSE")
