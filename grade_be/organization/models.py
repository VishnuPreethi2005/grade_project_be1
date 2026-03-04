from authentication.models import Organization, User
from django.db import models
from django.utils import timezone
import uuid


class Test(models.Model):
    """
    Model representing a test or exam within an organization.

    Attributes:
        title (str): The title of the test.
        description (str): A description of the test.
        start_time (datetime): The start time of the test.
        duration_minutes (int): Duration of the test in minutes.
        organization (Organization): The organization this test belongs to.
        created_at (datetime): Timestamp when the test was created.
        updated_at (datetime): Timestamp when the test was last updated.
    """
    title = models.CharField(max_length=255)
    description = models.TextField()
    start_time = models.DateTimeField()
    duration_minutes = models.IntegerField()
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="tests", null=True, blank=True
    )
    # Scoping for multi-tenancy and hierarchy
    SCOPE_TYPES = (
        ("TENANT", "Tenant"),
        ("ORG_UNIT", "Organization Unit"),
    )
    scope_type = models.CharField(max_length=20, choices=SCOPE_TYPES, default="TENANT")
    scope_id = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Retake configuration
    max_retakes = models.PositiveIntegerField(
        default=5,
        help_text="Maximum number of retakes allowed for this test (1-10)"
    )

    # Scoping fields
    SCOPE_CHOICES = [
        ('TENANT', 'Tenant'),
        ('ORG_UNIT', 'Organization Unit'),
    ]
    scope_type = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='ORG_UNIT')
    scope_id = models.CharField(max_length=100, null=True, blank=True)
    
    # Assessment metadata (completing architecture)
    end_time = models.DateTimeField(null=True, blank=True)
    total_marks = models.IntegerField(null=True, blank=True)
    passing_marks = models.IntegerField(null=True, blank=True)

    def __str__(self) -> str:
        """
        Return a string representation of the test.

        Returns:
            str: The title of the test.
        """
        return self.title


class QuestionPaper(models.Model):
    """
    Model representing a question paper associated with a test.

    Attributes:
        test (Test): The test this question paper belongs to.
        pdf_file (File): The PDF file of the question paper.
        answer_key (File): The answer key file for the question paper.
        uploaded_at (datetime): Timestamp when the question paper was uploaded.
    """
    test = models.OneToOneField(
        Test, on_delete=models.CASCADE, related_name="question_paper"
    )
    pdf_file = models.FileField(upload_to="question_papers/organization")
    answer_key = models.FileField(upload_to="answer_keys/organization")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        """
        Return a string representation of the question paper.

        Returns:
            str: Description of the question paper and its test.
        """
        return f"Question Paper for {self.test.title}"


class TestAssignment(models.Model):
    """
    Model representing the assignment of a test to a student.

    Attributes:
        test (Test): The test assigned.
        student (User): The student assigned to the test.
        assigned_at (datetime): Timestamp when the assignment was created.
        is_completed (bool): Whether the test has been completed by the student.
        score (float): The score obtained by the student (nullable).
    """
    STATUS_CHOICES = (
        ("ASSIGNED", "Assigned"),
        ("IN_PROGRESS", "In Progress"),
        ("SUBMITTED", "Submitted"),
        ("EVALUATED", "Evaluated"),
    )

    test = models.ForeignKey(
        Test, on_delete=models.CASCADE, related_name="assignments"
    )
    student = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="test_assignments"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ASSIGNED")
    assigned_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)

    status = models.CharField(
        max_length=20, default="ASSIGNED"
    )  # ASSIGNED, STARTED, SUBMITTED
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("test", "student")

    def __str__(self) -> str:
        """
        Return a string representation of the test assignment.

        Returns:
            str: The student's email and the test title.
        """
        return f"{self.student.email} - {self.test.title}"


class StudentInvitation(models.Model):
    """
    Model representing an invitation sent to a student to join an organization.

    Attributes:
        email (str): The email address of the invitee.
        organization (Organization): The organization sending the invitation.
        token (UUID): Unique token for the invitation.
        status (str): The status of the invitation (pending, accepted, etc.).
        created_at (datetime): Timestamp when the invitation was created.
        expires_at (datetime): Timestamp when the invitation expires.
        accepted_at (datetime): Timestamp when the invitation was accepted (nullable).
    """
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("expired", "Expired"),
    )

    email = models.EmailField()
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="invitations"
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default="pending"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        """
        Return a string representation of the invitation.

        Returns:
            str: Description of the invitation and organization.
        """
        return f"Invitation for {self.email} to {self.organization.name}"

    def is_expired(self) -> bool:
        """
        Check if the invitation has expired.

        Returns:
            bool: True if the invitation is expired, False otherwise.
        """
        return timezone.now() > self.expires_at

    def save(self, *args, **kwargs) -> None:
        """
        Save the invitation, setting the expiration date if not already set.
        """
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)


class TestQuestion(models.Model):
    """
    Model representing a question in a test's question paper.

    Attributes:
        question_text (str): The text of the question.
        question_type (str): The type of the question (e.g., MCQ, descriptive).
        marks (int): The marks assigned to the question.
        options (JSON): Options for MCQ/matching questions.
        correct_answer (str): The correct answer for the question.
        model_answer (str): Model answer for descriptive questions.
        keywords (JSON): Keywords for descriptive questions.
        order (int): The order of the question in the paper.
        question_paper (QuestionPaper): The question paper this question belongs to.
        programming_language (str): Programming language for programming questions.
        test_cases (JSON): Test cases for programming questions.
        time_limit (int): Time limit for programming questions (seconds).
        memory_limit (int): Memory limit for programming questions (MB).
    """
    QUESTION_TYPES = [
        ("mcq", "Multiple Choice"),
        ("descriptive", "Descriptive"),
        ("true_false", "True/False"),
        ("programming", "Programming"),
        ("fill_blank", "Fill in the Blank"),
        ("matching", "Matching"),
        ("short_answer", "Short Answer"),
        ("long_answer", "Long Answer"),
    ]

    id = models.BigAutoField(primary_key=True)
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    marks = models.PositiveIntegerField()
    # For MCQ, matching, etc.
    options = models.JSONField(blank=True, null=True)
    correct_answer = models.TextField()
    model_answer = models.TextField(
        blank=True, null=True
    )  # For descriptive questions
    keywords = models.JSONField(
        blank=True, null=True
    )  # For descriptive questions
    order = models.PositiveIntegerField()
    question_paper = models.ForeignKey(
        QuestionPaper, on_delete=models.CASCADE, related_name="test_questions"
    )
    # For programming questions
    programming_language = models.CharField(
        max_length=50, blank=True, null=True
    )
    test_cases = models.JSONField(blank=True, null=True)  # List of test cases
    time_limit = models.PositiveIntegerField(
        default=5
    )  # Time limit in seconds
    is_digitized = models.BooleanField(default=False)
    memory_limit = models.PositiveIntegerField(
        default=512
    )  # Memory limit in MB
    
    # Digitization Support
    is_digitized = models.BooleanField(default=False)
    digitization_source_file = models.FileField(upload_to="digitization/source/", null=True, blank=True)
    ai_generated_tags = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        """
        Return a string representation of the test question.

        Returns:
            str: The question type and a snippet of the question text.
        """
        return f"{self.question_type} - {self.question_text[:50]}"


class StudentAnswer(models.Model):
    """
    Model representing a student's answer to a test question.

    Attributes:
        test (Test): The test the answer belongs to.
        student (User): The student who submitted the answer.
        question (TestQuestion): The question being answered.
        answer_text (str): The student's answer text.
        submitted_at (datetime): Timestamp when the answer was submitted.
        is_evaluated (bool): Whether the answer has been evaluated.
        score (float): The score obtained for this answer (nullable).
    """
    test = models.ForeignKey(
        Test, on_delete=models.CASCADE, related_name="student_answers",
        null=True, blank=True
    )
    student = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="submitted_answers",
        null=True, blank=True
    )
    test_assignment = models.ForeignKey(
        TestAssignment, on_delete=models.CASCADE, related_name="answers",
        null=True, blank=True
    )
    question = models.ForeignKey(
        TestQuestion,
        on_delete=models.CASCADE,
        related_name="student_responses",
    )
    answer_text = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_evaluated = models.BooleanField(default=False)
    score = models.FloatField(null=True, blank=True)
    feedback = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("test", "student", "question")
        ordering = ["submitted_at"]

    def __str__(self) -> str:
        """
        Return a string representation of the student's answer.

        Returns:
            str: Description of the answer, student, and test.
        """
        return f"Answer by {self.student.email} for {self.question.question_text[:30]}... in {self.test.title}"


class OrganizationHierarchyLevel(models.Model):
    """
    Represents a level in the organization's hierarchy (e.g., Department, Year, Class).

    Attributes:
        organization (Organization): The organization this hierarchy level belongs to.
        name (str): The name of the hierarchy level.
        description (str): Description of the hierarchy level.
        order (int): The order of the hierarchy level.
        is_active (bool): Whether the hierarchy level is active.
        parent (OrganizationHierarchyLevel): The parent hierarchy level (nullable).
        created_at (datetime): Timestamp when the level was created.
        updated_at (datetime): Timestamp when the level was last updated.
    """
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="hierarchy_levels"
    )
    # e.g., "Department", "Year", "Class"
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField()  # To maintain the hierarchy order
    is_active = models.BooleanField(default=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("organization", "name")
        ordering = ["order"]
        db_table = "organization_hierarchy_level"

    def __str__(self) -> str:
        """
        Return a string representation of the hierarchy level.

        Returns:
            str: The organization name and hierarchy level name.
        """
        return f"{self.organization.name} - {self.name}"


class HierarchyValue(models.Model):
    """
    Represents a value for a hierarchy level (e.g., "Computer Science" for Department).

    Attributes:
        hierarchy_level (OrganizationHierarchyLevel): The hierarchy level this value belongs to.
        value (str): The value for the hierarchy level.
        description (str): Description of the value.
        is_active (bool): Whether the value is active.
        created_at (datetime): Timestamp when the value was created.
        updated_at (datetime): Timestamp when the value was last updated.
    """
    hierarchy_level = models.ForeignKey(
        OrganizationHierarchyLevel,
        on_delete=models.CASCADE,
        related_name="values",
    )
    # e.g., "Computer Science", "2023", "A"
    value = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children_values"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("hierarchy_level", "value")
        db_table = "organization_hierarchy_value"

    def __str__(self) -> str:
        """
```
        Return a string representation of the hierarchy value.

        Returns:
            str: The hierarchy level name and value.
        """
        return f"{self.hierarchy_level.name} - {self.value}"





class UserHierarchyMembership(models.Model):
    """
    Links users (Students/Teachers) to hierarchy nodes.
    Replaces/Aliases StudentHierarchy for strict adherence to spec.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="hierarchy_memberships")
    hierarchy_value = models.ForeignKey(HierarchyValue, on_delete=models.CASCADE, related_name="members")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('user', 'hierarchy_value')

    def __str__(self):
        return f"{self.user.email} in {self.hierarchy_value}"
    
class Assignment(models.Model):
    """
    Stores the core details of an assignment created by an evaluator.
    Links to the User, Organization, and the HierarchyValues it's assigned to.
    """
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    due_date = models.DateTimeField()
    points = models.PositiveIntegerField(default=100)

    # Relationships from your documentation
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_assignments"
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="assignments"
    )
    assigned_to = models.ManyToManyField(
        HierarchyValue,
        related_name="assignments" # Changed from 'assignments_assigned' for simplicity
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-due_date']

    def __str__(self):
        return f"{self.title} ({self.organization.name})"


class AssignmentAttachment(models.Model):
    """
    Stores instruction files (e.g., PDF, ZIP) uploaded by the evaluator for an assignment.
    """
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="attachments"
    )
    file = models.FileField(upload_to='assignments/attachments/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for {self.assignment.title}"


class Submission(models.Model):
    """
    Represents a student's submission for a given assignment.
    This is the updated and recommended version.
    """
    # Expanded status choices to handle all workflow stages, including future AI grading
    class SubmissionStatus(models.TextChoices):
        SUBMITTED = 'SUBMITTED', 'Submitted'
        LATE = 'LATE', 'Late'
        GRADED = 'GRADED', 'Graded'
        PENDING_AI = 'PENDING_AI', 'Pending AI Grading'
        AI_REVIEW_READY = 'AI_REVIEW_READY', 'AI Review Ready'

    assignment = models.ForeignKey(
        'Assignment',  # Use quotes if Assignment is defined later in the file
        on_delete=models.CASCADE,
        related_name="submissions"
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="assignment_submissions"
    )
    status = models.CharField(
        max_length=20,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.SUBMITTED # Default to SUBMITTED as it's created on submission
    )
    # Using default=timezone.now sets the submission time when the object is created in Python
    submitted_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Grading Fields ---
    # Manual Grading
    grade = models.IntegerField(null=True, blank=True)
    feedback = models.TextField(null=True, blank=True)
    
    # AI Grading (for future implementation)
    ai_grade = models.IntegerField(null=True, blank=True)
    ai_feedback = models.TextField(null=True, blank=True)
    plagiarism_score = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ('assignment', 'student')
        ordering = ['-submitted_at']

    def save(self, *args, **kwargs):
        """
        Overridden save method to automatically set the status to LATE on creation if needed.
        This logic now only runs when the object is first created.
        """
        if self.pk is None:
            # Check if the submission time is after the due date upon first save
            if self.submitted_at > self.assignment.due_date:
                self.status = self.SubmissionStatus.LATE
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Submission by {self.student.email} for {self.assignment.title}"

class SubmissionFile(models.Model):
    """
    Stores files uploaded by a student as part of their submission.
    """
    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name="files"
    )
    file = models.FileField(upload_to='assignments/submissions/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"File for submission by {self.submission.student.email}"    


class TestDelegation(models.Model):
    """
    Delegates a Test to a specific user (Coordinator) for management.
    """
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name="delegations")
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="test_delegations"
    )
    role_type = models.CharField(max_length=50, default="COORDINATOR")
    can_manage_students = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Delegation: {self.test.title} -> {self.user.email}"


class EvaluationAssignment(models.Model):
    """
    Assigns a specific student answer to an evaluator.
    """
    test = models.ForeignKey(
        Test, on_delete=models.CASCADE, related_name="evaluation_assignments", null=True
    )
    student_answer = models.ForeignKey(
        StudentAnswer, on_delete=models.CASCADE, related_name="evaluation_assignments"
    )
    evaluator = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="evaluations_assigned"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, default="PENDING"
    )  # PENDING, IN_PROGRESS, COMPLETED

    def __str__(self):
        return f"Eval Assignment: {self.student_answer.id} -> {self.evaluator.email}"


class AuditLog(models.Model):
    """
    Tracks security and compliance events.
    """
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="audit_logs")
    action = models.CharField(max_length=50) # LOGIN, CREATE, UPDATE, DELETE
    target_model = models.CharField(max_length=100)
    target_id = models.CharField(max_length=100)
    details = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} by {self.actor} on {self.target_model}"
