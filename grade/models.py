from django.db import models
from authentication.models import User as App, Organization, Role
from organization.models import Test, TestQuestion, StudentAnswer
from django.utils import timezone
from datetime import timedelta
from django.core.validators import FileExtensionValidator
from dataclasses import dataclass
from typing import Optional
import re
import json
import os
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Filename Metadata Extraction Utilities
# ============================================================================
# These utilities extract metadata from answer key and reference image filenames.
# Expected filename pattern: <board>_<class>_<subject>_<qpcode>set<setnumber>_<year>_<number>.<ext>
# Example: cbse_12_chemistry_56Bset5_2023_70_answer.json


@dataclass
class ExtractedMetadata:
    """Holds extracted metadata from a filename."""
    board: Optional[str] = None
    class_level: Optional[str] = None
    subject: Optional[str] = None
    qp_code: Optional[str] = None
    set_number: Optional[str] = None
    year: Optional[int] = None
    question_number: Optional[str] = None  # For assets only (e.g., "Q24a")
    is_answer_key: bool = False
    is_asset: bool = False


def extract_metadata_from_filename(filename: str) -> ExtractedMetadata:
    """
    Extract QP metadata from standardized filename.
    
    Expected formats:
    - cbse_12_chemistry_56Bset5_2023_70_answer.json  -> Answer key
    - cbse_12_chemistry_56Bset5_2023_70_Q24a.jpg     -> Asset/reference image
    
    Args:
        filename: The filename (with or without path) to parse
        
    Returns:
        ExtractedMetadata object with extracted fields
    """
    metadata = ExtractedMetadata()
    
    # Get just the filename without path
    basename = os.path.basename(filename)
    # Remove extension
    name_no_ext = os.path.splitext(basename)[0]
    
    logger.debug(f"Parsing filename: {name_no_ext}")
    
    # Check if it's an answer key (ends with _answer)
    if name_no_ext.endswith("_answer"):
        metadata.is_answer_key = True
        name_no_ext = name_no_ext[:-7]  # Remove "_answer" suffix
    
    # Check if it's an asset (contains _Q followed by question number)
    asset_match = re.search(r'_Q([A-Za-z0-9]+)$', name_no_ext)
    if asset_match:
        metadata.is_asset = True
        metadata.question_number = "Q" + asset_match.group(1)
        name_no_ext = name_no_ext[:asset_match.start()]
    
    # Split by underscore
    parts = name_no_ext.split('_')
    
    if len(parts) < 4:
        logger.warning(f"Filename has fewer parts than expected: {parts}")
        return metadata
    
    # Extract board (first part)
    metadata.board = parts[0].upper() if parts[0] else None
    
    # Extract class level (second part)
    metadata.class_level = parts[1] if len(parts) > 1 else None
    
    # Extract subject (third part)
    metadata.subject = parts[2].capitalize() if len(parts) > 2 else None
    
    # Extract qp_code and set_number from the fourth part (e.g., "56Bset5")
    if len(parts) > 3:
        qp_set_part = parts[3]
        qp_set_match = re.match(r'^([A-Za-z0-9]+?)set(\d+)$', qp_set_part, re.IGNORECASE)
        if qp_set_match:
            metadata.qp_code = qp_set_match.group(1).upper()
            metadata.set_number = qp_set_match.group(2)
        else:
            metadata.qp_code = qp_set_part.upper()
    
    # Extract year (look for 4-digit number)
    for part in parts:
        if part.isdigit() and len(part) == 4:
            try:
                year_val = int(part)
                if 2000 <= year_val <= 2100:
                    metadata.year = year_val
                    break
            except ValueError:
                pass
    
    logger.debug(f"Extracted metadata: {metadata}")
    return metadata


def generate_test_title(metadata: ExtractedMetadata) -> str:
    """
    Generate a human-readable test title from extracted metadata.
    
    Args:
        metadata: ExtractedMetadata object
        
    Returns:
        A formatted test title string
    """
    parts = []
    if metadata.board:
        parts.append(metadata.board)
    if metadata.class_level:
        parts.append(f"Class {metadata.class_level}")
    if metadata.subject:
        parts.append(metadata.subject)
    if metadata.qp_code:
        parts.append(f"QP {metadata.qp_code}")
    if metadata.set_number:
        parts.append(f"Set {metadata.set_number}")
    if metadata.year:
        parts.append(str(metadata.year))
    
    return " - ".join(parts) if parts else "Unknown Paper"


# ============================================================================
# Models
# ============================================================================

class GradingResult(models.Model):
    """Stores AI-powered grading results for a student's answer upload.Add commentMore actions

    This model links to an `AnswerUpload` and contains the calculated score,
    paths to result files, and metadata about the grading process.

    Attributes:
        answer_upload: A one-to-one relationship to the `AnswerUpload` model.
        user_id: The ID of the user who submitted the answer.
        total_score: The total score awarded after grading.
        max_possible_score: The maximum possible score for the test.
        percentage: The calculated percentage score.
        result_json_path: The file path to the detailed JSON grading results.
        grading_processed: A boolean indicating if grading is complete.
        grading_error: Stores any error messages encountered during grading.
        created_at: The timestamp when the grading result was created.
        graded_at: The timestamp when the grading was completed.
        questions_count: The total number of questions in the test.
        diagrams_count: The total number of diagrams detected.
    """
    # Link to the answer upload (ForeignKey to support multiple attempts)
    answer_upload = models.ForeignKey(
        "AnswerUpload", on_delete=models.CASCADE, related_name="grading_results"
    )

    # Grading metadata
    user_id = models.CharField(max_length=100)  # Match with AnswerUpload
    total_score = models.FloatField(default=0)
    max_possible_score = models.FloatField(default=0)
    percentage = models.FloatField(default=0)

    # File paths for storing results
    result_json_path = models.CharField(max_length=500, null=True, blank=True)

    # Grading status
    grading_processed = models.BooleanField(default=False)
    grading_error = models.TextField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(null=True, blank=True)

    # Additional metadata
    questions_count = models.IntegerField(default=0)
    diagrams_count = models.IntegerField(default=0)

    class Meta:
        db_table = "grading_results"
        indexes = [
            models.Index(fields=["user_id"]),
            models.Index(fields=["answer_upload"]),
            models.Index(fields=["created_at"]),
            #models.Index(fields=["student_answer"]),
        ]

    def __str__(self) -> str:
        return f"Grading for Answer {self.answer_upload.id} - {self.total_score}/{self.max_possible_score}"

    def get_result_data(self) -> dict:
        """Load and return the grading result JSON data.Add commentMore actions

        Reads the JSON file specified by `result_json_path` and returns its
        contents as a dictionary.

        Returns:
            A dictionary containing the grading data, or None if the path
            does not exist. Returns a dictionary with an 'error' key if
            loading fails.
        """        
        if self.result_json_path and os.path.exists(self.result_json_path):
            try:
                with open(self.result_json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                return {"error": f"Failed to load result data: {str(e)}"}
        return None

# models.py

class QuestionGrade(models.Model):
    """Stores detailed grading for a single question."""
    grading_result = models.ForeignKey(
        GradingResult, on_delete=models.CASCADE, related_name="question_grades"
    )
    question_number = models.CharField(max_length=50)  # e.g., "Q1", "Q3a"
    question_type = models.CharField(max_length=50, null=True, blank=True)
    allocated_marks = models.FloatField()
    obtained_marks = models.FloatField()
    
    # Content
    student_answer = models.JSONField(null=True, blank=True)
    expected_answer = models.JSONField(null=True, blank=True)
    
    # Feedback & Analysis
    summary = models.TextField(null=True, blank=True)
    mistakes_identified = models.JSONField(default=list)  # List of strings
    final_feedback = models.TextField(null=True, blank=True)
    general_feedback = models.TextField(null=True, blank=True)
    diagram_comparison = models.TextField(null=True, blank=True)

    # Concept Analysis & Confidence
    concept_analysis = models.JSONField(null=True, blank=True)
    confidence_percentage = models.FloatField(null=True, blank=True)
    confidence_level = models.CharField(max_length=20, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['question_number']


class CriteriaGrade(models.Model):
    """Stores the breakdown of a specific evaluation criterion for a question."""
    question_grade = models.ForeignKey(
        QuestionGrade, on_delete=models.CASCADE, related_name="criteria_grades"
    )
    criterion_text = models.TextField()
    allocated_marks = models.FloatField()
    obtained_marks = models.FloatField()
    feedback = models.TextField(null=True, blank=True)
    mistakes_found = models.JSONField(default=list)

    class Meta:
        verbose_name_plural = "Criteria Grades"


class AIMetrics(models.Model):
    """Stores token usage and cost metrics for OCR and Grading processes."""
    PROCESS_CHOICES = [
        ('OCR', 'OCR'),
        ('GRADING', 'Grading'),
    ]
    
    answer_upload = models.ForeignKey(
        "AnswerUpload", on_delete=models.CASCADE, related_name="ai_metrics",
        null=True, blank=True
    )
    student_answer = models.ForeignKey(
        "organization.StudentAnswer", on_delete=models.CASCADE, related_name="ai_metrics",
        null=True, blank=True
    )
    process_type = models.CharField(max_length=20, choices=PROCESS_CHOICES)
    
    # For Grading, this matches the Question Number. For OCR, the function name.
    identifier = models.CharField(max_length=100) 
    
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    
    total_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    
    # Timestamp from the CSV log
    timestamp = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

class BaseQuestionPaper(models.Model):
    """An abstract base model for various types of question papers.Add commentMore actions

    This model provides common fields for question papers, such as title,
    subject, and total marks. It is not intended to be used directly but
    inherited by concrete question paper models.

    Attributes:
        organization: The organization to which this paper belongs.
        updated_by: The email of the user who last updated the paper.
        upload_date: The date when the paper was uploaded.
        test_title: The title of the test or question paper.
        board: The educational board (e.g., CBSE, ICSE).
        subject: The subject of the test.
        questions: A JSON field containing a list of questions.
        total_marks: The total marks for the paper.
        total_questions: The total number of questions in the paper.
    """
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="%(class)s_papers",
        null=True,
        blank=True,
    )
    updated_by = models.EmailField(
        null=True, blank=True
    )  # Email of the uploader
    upload_date = models.DateTimeField(auto_now_add=True)
    test_title = models.CharField(max_length=255, null=True, blank=True)
    board = models.CharField(max_length=50, null=True, blank=True)
    subject = models.CharField(max_length=100, null=True, blank=True)
    questions = models.JSONField(default=list, null=True, blank=True)
    total_marks = models.IntegerField(default=0)
    total_questions = models.IntegerField(default=0)
    
    # Retake configuration
    max_retakes = models.PositiveIntegerField(
        default=5,
        help_text="Maximum number of retakes allowed for this question paper (1-10)"
    )

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return f"{self.test_title} - {self.subject} ({self.board})"


class Questions(BaseQuestionPaper):
    """Represents a generic question paper uploaded to the system.Add commentMore actions

    This model inherits from `BaseQuestionPaper` and is used for
    storing general question papers that do not fall into other specific
    categories like 'sample' or 'previous year'.

    Attributes:
        file: The uploaded question paper file.
    """
    file = models.FileField(upload_to="question_papers/qp_uploader")


class SampleQuestionPaper(BaseQuestionPaper):
    """Represents a sample question paper.Add commentMore actions

    This model is used for storing sample question papers for practice.

    Attributes:
        file: The uploaded sample question paper file.
    """
    file = models.FileField(upload_to="question_papers/sample/")

class PreviousYearQuestionPaper(BaseQuestionPaper):
    """Represents a question paper from a previous year.

    This model stores metadata about previous year question papers.
    Question paper files are NOT uploaded (copyright reasons) - instead,
    the frontend provides links to official download websites.
    
    Records are created from answer key/reference image uploads,
    with metadata (board, subject, year, qp_code, set_number) 
    extracted automatically from filenames.

    Attributes:
        year: The year the question paper is from.
        set_number: The official set number for the paper (extracted from filename).
        qp_code: The official question paper code (extracted from filename).
        answer_key: The uploaded answer key file (PDF or JSON format).
        answer_key_uploaded_at: Timestamp when the answer key was uploaded.
        assets: Dictionary mapping question numbers to reference image paths.
    """
    # NOTE: No 'file' field - QP files are not uploaded due to copyright.
    # Frontend provides links to official websites instead.
    
    year = models.PositiveIntegerField(null=True, blank=True)
    # Metadata fields - extracted from answer key/asset filenames
    set_number = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Official set number for this previous year question paper (auto-extracted from filename).",
    )
    qp_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Official question paper code (QP code) for this paper (auto-extracted from filename).",
    )
    answer_key = models.FileField(
        upload_to="answer_keys/previous_year/",
        blank=True,
        null=True,
        help_text="Upload the answer key (PDF or JSON). JSON is recommended for higher accuracy.",
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'json'])]
    )
    
    answer_key_uploaded_at = models.DateTimeField(blank=True, null=True)
    
    # Store asset mapping: {"Q3": "path/to/asset.pdf", ...}
    assets = models.JSONField(default=dict, blank=True)

    # Transient fields for Admin UI Upload
    new_asset_file = models.FileField(
        upload_to="question_papers/previous_year/assets/",
        blank=True,
        null=True,
        help_text="Upload a single asset here to add it to the Assets list."
    )
    new_asset_label = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        help_text="Question Number (e.g. 'Q4'). LEAVE BLANK to auto-extract from filename (e.g. '..._Q4.png')"
    )

    class Meta:
        indexes = [
            models.Index(fields=['qp_code', 'set_number']),
            models.Index(fields=['board', 'subject', 'year']),
        ]

    def save(self, *args, **kwargs):
        """Override save to handle metadata extraction and transient uploads.
        
        Extracts metadata from answer key filename since question paper
        files are not uploaded (copyright reasons).
        
        Uses extract_metadata_from_filename utility for enhanced parsing.
        """
        # Functions are now defined at module level in this file
        
        # Extract metadata from answer key filename
        source_file = None
        if self.answer_key:
            source_file = self.answer_key.name
        
        # Auto-extract metadata if fields are missing
        if source_file and (not self.year or not self.board or not self.subject or not self.qp_code or not self.set_number):
            try:
                metadata = extract_metadata_from_filename(source_file)
                
                # Apply extracted metadata only if fields are missing
                if not self.board and metadata.board:
                    self.board = metadata.board
                if not self.subject and metadata.subject:
                    self.subject = metadata.subject
                if not self.year and metadata.year:
                    self.year = metadata.year
                if not self.qp_code and metadata.qp_code:
                    self.qp_code = metadata.qp_code
                if not self.set_number and metadata.set_number:
                    self.set_number = metadata.set_number
                
                # Generate test title if missing
                if not self.test_title:
                    self.test_title = generate_test_title(metadata)

            except Exception as e:
                # Log error but don't block save
                print(f"Metadata extraction failed: {e}")

        if self.answer_key and not self.answer_key_uploaded_at:
            from django.utils import timezone
            self.answer_key_uploaded_at = timezone.now()
            
        super().save(*args, **kwargs)
        
        # Post-Save Logic for Asset
        if self.new_asset_file:
            try:
                # The file is now on disk
                file_path = self.new_asset_file.name 
                file_name_clean = os.path.splitext(os.path.basename(file_path))[0]
                
                label_to_use = self.new_asset_label
                
                # Auto-extract logic if label is missing
                if not label_to_use:
                    if "_Q" in file_name_clean:
                        # Split by last occurrence of _Q
                        try:
                            _, q_suffix = file_name_clean.rsplit("_Q", 1)
                            # Allow alphanumeric, dots, and hyphens (e.g. 4, 3a, 3.1, 3-ii)
                            if all(c.isalnum() or c in ".-" for c in q_suffix):
                                label_to_use = "Q" + q_suffix
                        except ValueError:
                            pass
                
                if label_to_use:
                    if not self.assets: self.assets = {}
                    self.assets[label_to_use] = file_path
                    
                    # Clear fields using update to avoid recursion
                    PreviousYearQuestionPaper.objects.filter(pk=self.pk).update(
                        assets=self.assets,
                        new_asset_file=None,
                        new_asset_label=None
                    )
                    self.refresh_from_db()
                else:
                    print(f"Could not determine label for asset: {file_path}")
                    
            except Exception as e:
                print(f"Error processing asset upload: {e}")


class GeneratedQuestionPaper(BaseQuestionPaper):
    """Represents a question paper generated by the system.

    These papers are typically created on-demand for users.

    Attributes:
        file: The generated question paper file.
        user_id: The ID of the user for whom the paper was generated.
    """
    file = models.FileField(upload_to="question_papers/generated/")
    # Or models.ForeignKey if you have a User model
    user_id = models.CharField(App, max_length=255, null=True, blank=True)


class AnswerUpload(models.Model):
    """Stores answer sheets uploaded by users for grading.

    This model links an uploaded answer file to a specific question paper
    and user. It also tracks the status of Optical Character Recognition (OCR)
    processing.

    Attributes:
        file: The uploaded answer sheet file.
        user_id: The ID of the user who uploaded the answer sheet.
        organization: The organization associated with the user.
        question_paper_type: The type of question paper (e.g., 'sample', 'generated').
        question_paper_id: The ID of the associated question paper.
        upload_date: The timestamp of the upload.
        ocr_updated_at: The timestamp when OCR processing was last updated.
        sample_question_paper: FK to `SampleQuestionPaper`.
        previous_year_question_paper: FK to `PreviousYearQuestionPaper`.
        generated_question_paper: FK to `GeneratedQuestionPaper`.
        organization_test: FK to `organization.Test`.
        questions: FK to `Questions`.
        ocr_processed: A boolean indicating if OCR processing is complete.
        ocr_json_path: File path to the OCR results in JSON format.
        ocr_images_dir: Directory path for images extracted during OCR.
        ocr_error: Stores any errors from the OCR process.
        ocr_processed_at: Timestamp when OCR processing was completed.
    """
    # Your existing fields...
    file = models.FileField(upload_to="answer_uploads/")
    # Or models.ForeignKey if you have a User model
    user_id = models.IntegerField(null=True, blank=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="answer_uploads",
        null=True,
        blank=True,
    )
    question_paper_type = models.CharField(max_length=20)
    question_paper_id = models.IntegerField(null=True, blank=True)
    upload_date = models.DateTimeField(auto_now_add=True)
    ocr_updated_at = models.DateTimeField(null=True, blank=True)

    # Foreign key relationships (your existing code)
    sample_question_paper = models.ForeignKey(
        "grade.SampleQuestionPaper", on_delete=models.CASCADE, null=True, blank=True
    )
    previous_year_question_paper = models.ForeignKey(
        "grade.PreviousYearQuestionPaper",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    generated_question_paper = models.ForeignKey(
        "grade.GeneratedQuestionPaper",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    organization_test = models.ForeignKey(
        "organization.Test", on_delete=models.CASCADE, null=True, blank=True
    )
    questions = models.ForeignKey(
        "grade.Questions", on_delete=models.CASCADE, null=True, blank=True
    )

    # New OCR-related fields
    ocr_processed = models.BooleanField(default=False)
    ocr_json_path = models.CharField(max_length=500, null=True, blank=True)
    ocr_images_dir = models.CharField(max_length=500, null=True, blank=True)
    roll_number = models.CharField(max_length=20, null=True, blank=True)
    ocr_error = models.TextField(null=True, blank=True)
    ocr_processed_at = models.DateTimeField(null=True, blank=True)
    
    # Attempt tracking for retakes
    attempt_number = models.PositiveIntegerField(
        default=1,
        help_text="Attempt number for this test submission (1 = first attempt)"
    )

    class Meta:
        unique_together = (
            "user_id",
            "question_paper_type",
            "question_paper_id",
            "attempt_number",  # Allow multiple attempts per user/paper
        )
        indexes = [
            models.Index(fields=["user_id", "question_paper_type", "question_paper_id"]),
        ]


class QuestionFeedback(models.Model):
    """Stores feedback provided for a specific answer upload.Add commentMore actions

    This model is intended for overall feedback on an entire answer sheet.

    Attributes:
        answer_upload: A foreign key to the `AnswerUpload` model.
        feedback_text: The text of the feedback.
        marks_obtained: The total marks obtained for the answer sheet.
        created_date: The timestamp when the feedback was created.
    """
    answer_upload = models.ForeignKey(
        AnswerUpload, on_delete=models.CASCADE, related_name="feedback"
    )
    feedback_text = models.TextField(null=True, blank=True)
    marks_obtained = models.IntegerField(default=0)
    created_date = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Feedback for {self.answer_upload}"


class AnswerAssignment(models.Model):
    """Tracks the assignment of answer sheets to human evaluators.Add commentMore actions

    This model ensures that each answer sheet is assigned to an evaluator
    and tracks the completion status of the evaluation.

    Attributes:
        answer_upload: A one-to-one link to the `AnswerUpload`.
        evaluator: The `User` assigned to evaluate the answer sheet.
        assigned_date: The date the assignment was made.
        completed: A boolean indicating if the evaluation is complete.
    """
    answer_upload = models.OneToOneField(
        AnswerUpload, on_delete=models.CASCADE
    )
    evaluator = models.ForeignKey(
        App,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_answers",
    )
    assigned_date = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)

    def is_expired(self) -> bool:
        """Checks if the assignment is older than 3 days and not completed.Add commentMore actions

        Returns:
            True if the assignment is considered expired, False otherwise.
        """
        return not self.completed and (
            timezone.now() - self.assigned_date
        ) > timedelta(days=3)

    def __str__(self) -> str:
        return f"{self.answer_upload} -> {self.evaluator}"


class Feedback(models.Model):
    """Stores detailed, question-specific feedback for an answer upload.Add commentMore actions

    Unlike `QuestionFeedback`, this model holds feedback for each individual
    question in an answer sheet.

    Attributes:
        answer_upload: The associated `AnswerUpload`.
        question_number: The number of the question receiving feedback.
        marks_obtained: The marks awarded for the specific question.
        feedback: The textual feedback for the answer.
        complexity: The difficulty level of the question.
        marks_out_of: The maximum marks for the question.
        created_at: The timestamp when the feedback was created.
        updated_at: The timestamp when the feedback was last updated.
    """

    answer_upload = models.ForeignKey(
        AnswerUpload, related_name="feedbacks", on_delete=models.CASCADE
    )
    question_number = models.IntegerField()
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2)
    feedback = models.TextField()
    complexity = models.CharField(
        max_length=10,
        choices=[("easy", "Easy"), ("medium", "Medium"), ("hard", "Hard")],
    )

    marks_out_of = models.FloatField()

    complexity = models.CharField(
        max_length=10,
        choices=[("easy", "Easy"), ("medium", "Medium"), ("hard", "Hard")],
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Feedback for Question {self.question_number}"


class MentorshipRequest(models.Model):
    """Represents a request from a student to be mentored by a mentor.Add commentMore actions

    This model tracks the relationship request between a mentor and a student,
    including its status.

    Attributes:
        mentor: The `User` who is the potential mentor.
        student: The `User` who is the potential student.
        status: The status of the request (Pending, Accepted, Rejected).
        created_at: The timestamp of the request.
    """
    mentor = models.ForeignKey(
        App, related_name="sent_requests", on_delete=models.CASCADE
    )
    student = models.ForeignKey(
        App, related_name="received_requests", on_delete=models.CASCADE
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("Pending", "Pending"),
            ("Accepted", "Accepted"),
            ("Rejected", "Rejected"),
        ],
        default="Pending",
    )
    created_at = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    """Represents a notification sent from one user to another.Add commentMore actions

    This can be used for various purposes, including mentorship requests or
    general communication within the platform.
Add commentMore actions
    Attributes:
        sender: The `User` who sent the notification.
        recipient: The `User` who receives the notification.
        sender_role: The role of the sender.
        recipient_role: The role of the recipient.
        message: The content of the notification.
        created_at: The timestamp when the notification was created.
        is_read: A boolean indicating if the recipient has read it.
        mentor_request: A boolean indicating if this is related to a mentor request.
    """

    ROLE_CHOICES = [
        ("student", "Student"),
        ("admin", "Admin"),
        ("evaluator", "Evaluator"),
        ("mentor", "Mentor"),
    ]

    sender = models.ForeignKey(
        App, on_delete=models.CASCADE, related_name="sent_notifications"
    )
    recipient = models.ForeignKey(
        App, on_delete=models.CASCADE, related_name="received_notifications"
    )
    sender_role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default="mentor"
    )
    recipient_role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default="student"
    )
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    mentor_request = models.BooleanField(default=False)
    reference_id = models.IntegerField(null=True, blank=True)
    on_click_url = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self) -> str:
        return f"Notification from {self.sender} ({self.sender_role}) to {self.recipient} ({self.recipient_role}) - {'Read' if self.is_read else 'Unread'}"


class MentorStudent(models.Model):
    """Represents the established relationship between a mentor and a student.

    This model is created once a `MentorshipRequest` is accepted, formally
    linking a mentor and a student.

    Attributes:
        mentor: The `User` acting as the mentor.
        student: The `User` being mentored.
        created_at: Timestamp when the relationship was established.
    """
    mentor = models.ForeignKey(
        App, on_delete=models.CASCADE, related_name="mentored_students"
    )
    student = models.ForeignKey(
        App, on_delete=models.CASCADE, related_name="monitored_by_mentors"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Prevent duplicate mentor-student pairs
        unique_together = ("mentor", "student")


# class MainRequest(models.Model):
#     user = models.ForeignKey(App, on_delete=models.CASCADE, related_name='main_requests')
#     role = models.CharField(max_length=50)  # Role of the user
#     resume = models.FileField(upload_to='resumes/')  # Path to uploaded resumes
#     board = models.CharField(max_length=50, choices=[
#         ('CBSE', 'CBSE'),
#         ('ICSE', 'ICSE'),
#         ('Stateboard', 'Stateboard'),
#         ('Neet', 'NEET'),
#         ('Jee', 'JEE')
#     ])
#     subject = models.CharField(max_length=100)  # Subject entered by the user
# submitted_at = models.DateTimeField(auto_now_add=True)  # Timestamp for
# submission


#     def __str__(self):
#         return f"MainRequest by {self.user.username} for {self.role}"
class MainRequest(models.Model):
    """Represents a user's request to take on a specific role.

    This is used when a user applies to become a mentor or evaluator,
    submitting their resume and specifying their areas of expertise.

    Attributes:
        user: The user making the request.
        role: The role the user is applying for (e.g., 'mentor').
        resume: The user's uploaded resume file.
        board: The educational board the user is associated with.
        subject: The subject of expertise.
        submitted_at: The timestamp of the submission.
    """
    user = models.ForeignKey(
        App, on_delete=models.CASCADE, related_name="main_requests"
    )
    role = models.CharField(max_length=50)  # Role of the user
    resume = models.FileField(upload_to="resumes/")  # Path to uploaded resumes
    board = models.CharField(
        max_length=50,
        choices=[
            ("CBSE", "CBSE"),
            ("ICSE", "ICSE"),
            ("TNboard", "TNboard"),
            ("Neet", "NEET"),
            ("Jee", "JEE"),
        ],
        blank=True,  # Allows board field to be empty in forms
        null=True,  # Stores NULL in the database if empty
    )
    subject = models.CharField(
        max_length=100,
        blank=True,  # Allows subject field to be empty in forms
        null=True,  # Stores NULL in the database if empty
    )
    submitted_at = models.DateTimeField(
        auto_now_add=True
    )  # Timestamp for submission

    def __str__(self) -> str:
        return f"MainRequest by {self.user.username} for {self.role}"


# Define constants for exam types, complexity levels, and question types
EXAM_TYPES = [
    ("CBSE", "CBSE"),
    ("ICSE", "ICSE"),
    ("State Board", "State Board"),
    ("JEE", "JEE"),
    ("NEET", "NEET"),
]

COMPLEXITY_LEVELS = [
    ("easy", "Easy"),
    ("medium", "Medium"),
    ("hard", "Hard"),
]

QUESTION_TYPES = [
    ("multiple-choice", "Multiple Choice"),
    ("short-answer", "Short Answer"),
    ("long-answer", "Long Answer"),
]


class Question(models.Model):
    """Stores individual questions for various exams and subjects.Add commentMore actions

    This model defines the structure of a question, including its text, type,
    difficulty, and associated marks. It can also store images, options for
    multiple-choice questions, and detailed explanations.

    Attributes:
        subject: The subject of the question.
        topic: The specific topic within the subject.
        exam_type: The exam this question is relevant for (e.g., CBSE, NEET).
        complexity: The difficulty level (e.g., Easy, Medium, Hard).
        question_type: The format of the question (e.g., Multiple Choice).
        marks: The number of marks the question is worth.
        question_text: The main text of the question.
        question_image: An optional image accompanying the question.
        options: A JSON field for multiple-choice options.
        correct_answer: The correct answer or a detailed explanation.
        explanation: A text explanation for the solution.
        explanation_image: An optional image for the explanation.
        created_at: Timestamp when the question was created.
        updated_at: Timestamp when the question was last updated.
        is_submitted: A flag to track if the question has been submitted.
    """
    # General fields
    subject = models.CharField(max_length=100)
    topic = models.CharField(max_length=200)
    exam_type = models.CharField(max_length=50, choices=EXAM_TYPES)
    complexity = models.CharField(max_length=50, choices=COMPLEXITY_LEVELS)
    question_type = models.CharField(max_length=50, choices=QUESTION_TYPES)
    marks = models.PositiveIntegerField(default=1)

    # Question text and images
    question_text = models.TextField()
    question_image = models.ImageField(
        upload_to="question_images/", blank=True, null=True
    )

    # Options for multiple-choice questions
    # List of options (used for MCQ)
    options = models.JSONField(blank=True, null=True)
    correct_answer = models.TextField(
        blank=True, null=True
    )  # Correct answer or explanation

    # Explanation and solution fields
    explanation = models.TextField(blank=True, null=True)
    explanation_image = models.ImageField(
        upload_to="explanation_images/", blank=True, null=True
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # New field to track submission status
    is_submitted = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.subject} - {self.topic} - {self.question_type}"


class Evaluator(models.Model):
    """Stores individual questions for various exams and subjects.Add commentMore actions

    This model defines the structure of a question, including its text, type,
    difficulty, and associated marks. It can also store images, options for
    multiple-choice questions, and detailed explanations.

    Attributes:
        subject: The subject of the question.
        topic: The specific topic within the subject.
        exam_type: The exam this question is relevant for (e.g., CBSE, NEET).
        complexity: The difficulty level (e.g., Easy, Medium, Hard).
        question_type: The format of the question (e.g., Multiple Choice).
        marks: The number of marks the question is worth.
        question_text: The main text of the question.
        question_image: An optional image accompanying the question.
        options: A JSON field for multiple-choice options.
        correct_answer: The correct answer or a detailed explanation.
        explanation: A text explanation for the solution.
        explanation_image: An optional image for the explanation.
        created_at: Timestamp when the question was created.
        updated_at: Timestamp when the question was last updated.
        is_submitted: A flag to track if the question has been submitted.
    """
    user = models.OneToOneField(
        App, on_delete=models.CASCADE, related_name="evaluator_profile"
    )
    rating = models.FloatField(default=0.0)
    resume = models.FileField(upload_to="resumes/", blank=True, null=True)
    languages = models.ManyToManyField("Language", related_name="evaluators")
    subjects = models.ManyToManyField("Subject", related_name="evaluators")
    boards = models.ManyToManyField("Board", related_name="evaluators")

    def __str__(self) -> str:
        return f"Evaluator: {self.user.username} - Rating: {self.rating}"


class Language(models.Model):
    """Represents a language that can be associated with an evaluator.Add commentMore actions

    Attributes:
        name: The unique name of the language (e.g., 'English', 'Hindi').
    """
    name = models.CharField(max_length=100, unique=True)

    def __str__(self) -> str:
        return self.name


class Subject(models.Model):
    """Represents a subject that can be associated with an evaluator or question.Add commentMore actions

    Attributes:
        name: The unique name of the subject (e.g., 'Physics', 'Mathematics').
    """
    name = models.CharField(max_length=100, unique=True)

    def __str__(self) -> str:
        return self.name


class Board(models.Model):
    """Represents an educational board (e.g., CBSE, ICSE).Add commentMore actions

    Attributes:
        name: The unique name of the board.
    """

    name = models.CharField(max_length=50, unique=True)

    def __str__(self) -> str:
        return self.name


