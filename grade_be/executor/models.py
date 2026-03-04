from django.db import models


class Topic(models.Model):
    """
    Represents a topic associated with coding questions.

    Attributes:
        name (str): Unique name of the topic.
        created_at (datetime): Timestamp when the topic was created.
        updated_at (datetime): Timestamp when the topic was last updated.
    """
    name: str = models.CharField(max_length=100, unique=True)
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class Company(models.Model):
    """
    Represents a company that may have asked a coding question.

    Attributes:
        name (str): Unique name of the company.
    """
    name: str = models.CharField(max_length=100, unique=True)

    def __str__(self) -> str:
        return self.name


class Question(models.Model):
    """
    Represents a coding question with metadata and related topics/companies.

    Attributes:
        title (str): Title of the question.
        description (str): Full description of the problem.
        sample_input (str): Example input for understanding the problem.
        sample_output (str): Example output corresponding to the sample input.
        explanation (str): Optional explanation of the solution.
        constraints (str): Optional constraints related to input/output.
        testcase_description (str): Optional description of test cases.
        difficulty (str): Difficulty level - Easy, Medium, or Hard.
        topics (ManyToMany[Topic]): Topics associated with the question.
        companies (ManyToMany[Company]): Companies that have asked the question.
        year_asked (int): Optional year when the question was asked.
        custom_id (int): Auto-incremented custom ID to identify the question.
    """

    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]

    title: str = models.CharField(max_length=255)
    description: str = models.TextField()
    sample_input: str = models.TextField()
    sample_output: str = models.TextField()

    explanation: str = models.TextField(blank=True, null=True)
    constraints: str = models.TextField(blank=True, null=True)
    testcase_description: str = models.TextField(blank=True, null=True)

    difficulty: str = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='easy')
    topics = models.ManyToManyField(Topic, blank=True)
    companies = models.ManyToManyField(Company, blank=True)
    year_asked: int = models.PositiveIntegerField(blank=True, null=True)

    custom_id: int = models.PositiveIntegerField(unique=True, blank=True, null=True)

    def save(self, *args, **kwargs) -> None:
        """
        Override save method to auto-assign a unique custom_id if not set.
        """
        if self.custom_id is None:
            last_question = Question.objects.order_by('custom_id').last()
            self.custom_id = (last_question.custom_id + 1) if last_question else 1
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title


class TestCase(models.Model):
    """
    Represents a test case for a coding question.

    Attributes:
        question (ForeignKey): The question this test case is linked to.
        input_data (JSON): Input data to test the code.
        expected_output (JSON): Expected output from the user code.
        is_sample (bool): Indicates if it's a sample test case.
        test_type (str): Type of test case - Normal, Edge Case, or Boundary Case.
    """

    TEST_TYPE_CHOICES = [
        ("normal", "Normal"),
        ("edge", "Edge Case"),
        ("boundary", "Boundary Case"),
    ]

    question: Question = models.ForeignKey(Question, related_name='test_cases', on_delete=models.CASCADE)
    input_data: dict = models.JSONField()
    expected_output: dict = models.JSONField()
    is_sample: bool = models.BooleanField(default=False)
    test_type: str = models.CharField(max_length=10, choices=TEST_TYPE_CHOICES, default="normal")

    def __str__(self) -> str:
        return f"TestCase for Q{self.question.custom_id} [{self.test_type}]"



from django.db import models

class SiteSettings(models.Model):
    log_retention_days = models.PositiveIntegerField(default=7)

    def __str__(self):
        return f"Settings (retention: {self.log_retention_days} days)"

    class Meta:
        verbose_name = "Site Setting"
        verbose_name_plural = "Site Settings"


from authentication.models import User

class CodeSubmission(models.Model):
    """
    Represents a user's code submission for a coding question.
    """
    STATUS_CHOICES = [
        ('Accepted', 'Accepted'),
        ('Wrong Answer', 'Wrong Answer'),
        ('Time Limit Exceeded', 'Time Limit Exceeded'),
        ('Runtime Error', 'Runtime Error'),
        ('Compilation Error', 'Compilation Error'),
        ('Pending', 'Pending'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='code_submissions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='submissions')
    code = models.TextField()
    language = models.CharField(max_length=50, default='python')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Pending')
    submitted_at = models.DateTimeField(auto_now_add=True)
    runtime = models.FloatField(null=True, blank=True) # In seconds
    memory = models.FloatField(null=True, blank=True) # In MB

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.user.username} - {self.question.title} ({self.status})"
