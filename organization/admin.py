from django.contrib import admin
from .models import (
    Test,
    QuestionPaper,
    TestAssignment,
    StudentInvitation,
    TestQuestion,
    StudentAnswer,
    OrganizationHierarchyLevel,
    HierarchyValue,
    UserHierarchyMembership,
    Assignment, 
    AssignmentAttachment,
    Submission,
    SubmissionFile,
)
from django.utils.html import format_html
from django.utils import timezone


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    """
    Admin interface for the Test model.
    """
    list_display = (
        "id",
        "title",
        "description",
        "organization",
        "scope_type",
        "scope_id",
        "start_time",
        "duration_minutes",
        "created_at",
        "updated_at",
        "get_total_students",
        "get_total_questions",
    )
    list_filter = ("organization", "start_time", "created_at")
    search_fields = ("title", "description", "organization__name")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "title",
                    "description",
                    "organization",
                    "scope_type",
                    "scope_id",
                )
            },
        ),
        ("Test Details", {"fields": ("start_time", "duration_minutes")}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def get_total_students(self, obj):
        """
        Get the total number of students assigned to the test.

        Args:
            obj (Test): The test instance.

        Returns:
            int: Number of students assigned.
        """
        return obj.assignments.count()

    get_total_students.short_description = "Total Students"

    def get_total_questions(self, obj):
        """
        Get the total number of questions in the test's question paper.

        Args:
            obj (Test): The test instance.

        Returns:
            int: Number of questions in the question paper.
        """
        try:
            return obj.question_paper.test_questions.count()
        except BaseException:
            return 0

    get_total_questions.short_description = "Total Questions"


@admin.register(QuestionPaper)
class QuestionPaperAdmin(admin.ModelAdmin):
    """
    Admin interface for the QuestionPaper model.
    """
    list_display = (
        "id",
        "get_test_title",
        "get_organization",
        "pdf_file",
        "answer_key",
        "uploaded_at",
        "get_total_questions",
        "get_file_links",
    )
    list_filter = ("test__organization", "uploaded_at")
    search_fields = ("test__title", "test__organization__name")
    readonly_fields = ("uploaded_at",)

    def get_test_title(self, obj):
        """
        Get the title of the test associated with the question paper.

        Args:
            obj (QuestionPaper): The question paper instance.

        Returns:
            str: The test title or '-' if not available.
        """
        return obj.test.title if obj.test else "-"

    get_test_title.short_description = "Test Title"
    get_test_title.admin_order_field = "test__title"

    def get_organization(self, obj):
        """
        Get the organization name for the question paper.

        Args:
            obj (QuestionPaper): The question paper instance.

        Returns:
            str: The organization name or '-' if not available.
        """
        return (
            obj.test.organization.name
            if obj.test and obj.test.organization
            else "-"
        )

    get_organization.short_description = "Organization"
    get_organization.admin_order_field = "test__organization__name"

    def get_total_questions(self, obj):
        """
        Get the total number of questions in the question paper.

        Args:
            obj (QuestionPaper): The question paper instance.

        Returns:
            int: Number of questions in the question paper.
        """
        return obj.test_questions.count()

    get_total_questions.short_description = "Total Questions"

    def get_file_links(self, obj):
        """
        Get HTML links for the question paper and answer key files.

        Args:
            obj (QuestionPaper): The question paper instance.

        Returns:
            str: HTML links for the files.
        """
        links = []
        if obj.pdf_file:
            links.append(
                f'<a href="{obj.pdf_file.url}" target="_blank">Question Paper</a>'
            )
        if obj.answer_key:
            links.append(
                f'<a href="{obj.answer_key.url}" target="_blank">Answer Key</a>'
            )
        return format_html(" | ".join(links))

    get_file_links.short_description = "Files"

    fieldsets = (
        ("Test Information", {"fields": ("test",)}),
        ("Files", {"fields": ("pdf_file", "answer_key")}),
        ("Timestamps", {"fields": ("uploaded_at",), "classes": ("collapse",)}),
    )


@admin.register(TestQuestion)
class TestQuestionAdmin(admin.ModelAdmin):
    """
    Admin interface for the TestQuestion model.
    """
    list_display = (
        "id",
        "get_test_title",
        "get_organization",
        "question_text",
        "question_type",
        "marks",
        "order",
        "options",
        "correct_answer",
        "model_answer",
        "keywords",
        "programming_language",
        "test_cases",
        "time_limit",
        "memory_limit",
    )
    list_filter = ("question_type", "question_paper__test__organization")
    search_fields = (
        "question_text",
        "question_paper__test__title",
        "question_paper__test__organization__name",
    )
    readonly_fields = ()

    def get_test_title(self, obj):
        """
        Get the title of the test for the question.

        Args:
            obj (TestQuestion): The test question instance.

        Returns:
            str: The test title or '-' if not available.
        """
        return (
            obj.question_paper.test.title
            if obj.question_paper and obj.question_paper.test
            else "-"
        )

    get_test_title.short_description = "Test Title"

    def get_organization(self, obj):
        """
        Get the organization name for the test question.

        Args:
            obj (TestQuestion): The test question instance.

        Returns:
            str: The organization name or '-' if not available.
        """
        return (
            obj.question_paper.test.organization.name
            if obj.question_paper and obj.question_paper.test
            else "-"
        )

    get_organization.short_description = "Organization"

    fieldsets = (
        (
            "Question Information",
            {
                "fields": (
                    "question_paper",
                    "question_text",
                    "question_type",
                    "marks",
                    "order",
                )
            },
        ),
        (
            "Question Details",
            {
                "fields": (
                    "options",
                    "correct_answer",
                    "model_answer",
                    "keywords",
                )
            },
        ),
        (
            "Programming Question Details",
            {
                "fields": (
                    "programming_language",
                    "test_cases",
                    "time_limit",
                    "memory_limit",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Digitization Details",
            {
                "fields": (
                    "is_digitized",
                    "digitization_source_file",
                    "ai_generated_tags",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(TestAssignment)
class TestAssignmentAdmin(admin.ModelAdmin):
    """
    Admin interface for the TestAssignment model.
    """
    list_display = (
        "id",
        "get_test_title",
        "get_student_name",
        "get_student_email",
        "assigned_at",
        "status",
        "started_at",
        "completed_at",
        "score",
    )
    list_filter = ("status", "assigned_at", "test__organization")
    search_fields = ("test__title", "student__email", "student__full_name")
    readonly_fields = ("assigned_at",)

    def get_test_title(self, obj):
        """
        Get the title of the test for the assignment.

        Args:
            obj (TestAssignment): The test assignment instance.

        Returns:
            str: The test title.
        """
        return obj.test.title

    get_test_title.short_description = "Test Title"

    def get_student_name(self, obj):
        """
        Get the full name or username of the student for the assignment.

        Args:
            obj (TestAssignment): The test assignment instance.

        Returns:
            str: The student's full name or username.
        """
        return obj.student.full_name or obj.student.username

    get_student_name.short_description = "Student Name"

    def get_student_email(self, obj):
        """
        Get the email of the student for the assignment.

        Args:
            obj (TestAssignment): The test assignment instance.

        Returns:
            str: The student's email.
        """
        return obj.student.email

    get_student_email.short_description = "Student Email"

    fieldsets = (
        ("Assignment Details", {"fields": ("test", "student")}),
        ("Results", {"fields": ("status", "score")}),
        (
            "Timestamps",
            {
                "fields": ("assigned_at", "started_at", "completed_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(StudentInvitation)
class StudentInvitationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "email",
        "organization",
        "status",
        "created_at",
        "expires_at",
        "accepted_at",
        "is_expired_display",
    )
    list_filter = ("status", "organization", "created_at")
    search_fields = ("email", "organization__name")
    readonly_fields = ("created_at", "accepted_at")
    ordering = ("-created_at",)

    def is_expired_display(self, obj):
        is_expired = obj.is_expired()
        color = "red" if is_expired else "green"
        text = "Yes" if is_expired else "No"
        return format_html('<span style="color: {};">{}</span>', color, text)

    is_expired_display.short_description = "Expired"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Update expired status for invitations
        expired_invitations = qs.filter(
            status="pending", expires_at__lt=timezone.now()
        )
        expired_invitations.update(status="expired")
        return qs

    fieldsets = (
        (
            "Invitation Details",
            {"fields": ("email", "organization", "status")},
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "expires_at", "accepted_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(StudentAnswer)
class StudentAnswerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "test",
        "student",
        "question",
        "answer_text",
        "submitted_at",
        "is_evaluated",
        "score",
    )
    list_filter = (
        "test",
        "student",
        "question",
        "is_evaluated",
        "submitted_at",
    )
    search_fields = (
        "test__title",
        "student__email",
        "question__question_text",
        "answer_text",
    )
    readonly_fields = ("submitted_at",)
    fieldsets = (
        (
            "Submission Details",
            {"fields": ("test", "student", "question", "answer_text")},
        ),
        ("Evaluation Details", {"fields": ("is_evaluated", "score", "feedback")}),
        (
            "Timestamps",
            {"fields": ("submitted_at",), "classes": ("collapse",)},
        ),
    )


@admin.register(OrganizationHierarchyLevel)
class OrganizationHierarchyLevelAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "organization",
        "order",
        "is_active",
        "parent",
        "created_at",
    )
    list_filter = ("organization", "is_active", "parent")
    search_fields = ("name", "description")
    ordering = ("organization", "order")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Basic Information",
            {"fields": ("organization", "name", "description", "parent")},
        ),
        ("Configuration", {"fields": ("order", "is_active")}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(HierarchyValue)
class HierarchyValueAdmin(admin.ModelAdmin):
    list_display = ("value", "hierarchy_level", "is_active", "created_at")
    list_filter = (
        "hierarchy_level__organization",
        "hierarchy_level",
        "is_active",
    )
    search_fields = ("value", "description")
    ordering = ("hierarchy_level", "value")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Basic Information",
            {"fields": ("hierarchy_level", "value", "description")},
        ),
        ("Status", {"fields": ("is_active",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(UserHierarchyMembership)
class UserHierarchyMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "hierarchy_value", "created_at")
    list_filter = (
        "hierarchy_value__hierarchy_level__organization",
        "hierarchy_value__hierarchy_level",
    )
    search_fields = (
        "user__email",
        "user__full_name",
        "hierarchy_value__value",
    )
    ordering = ("user", "hierarchy_value__hierarchy_level__order")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Assignment", {"fields": ("user", "hierarchy_value")}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "user",
                "hierarchy_value",
                "hierarchy_value__hierarchy_level",
            )
        )
    
@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'organization', 'creator', 'due_date', 'points', 'created_at')
    list_filter = ('organization', 'due_date')
    search_fields = ('title', 'description', 'creator__email')
    ordering = ('-due_date',)
    # This helps in selecting the 'assigned_to' values more easily
    filter_horizontal = ('assigned_to',)

@admin.register(AssignmentAttachment)
class AssignmentAttachmentAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'file', 'uploaded_at')
    search_fields = ('assignment__title',)

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'student', 'status', 'grade', 'submitted_at')
    list_filter = ('status', 'assignment__organization')
    search_fields = ('assignment__title', 'student__email')
    ordering = ('-submitted_at',)

@admin.register(SubmissionFile)
class SubmissionFileAdmin(admin.ModelAdmin):
    list_display = ('submission', 'file', 'uploaded_at')
    search_fields = ('submission__assignment__title', 'submission__student__email')    
