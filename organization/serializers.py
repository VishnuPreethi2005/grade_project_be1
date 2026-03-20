from rest_framework import serializers
from authentication.models import User
from .models import (
    Test,
    QuestionPaper,
    TestAssignment,
    StudentAnswer,
    OrganizationHierarchyLevel,
    HierarchyValue,
    UserHierarchyMembership,
)
from typing import Any
from .models import Assignment, AssignmentAttachment, Submission, SubmissionFile


class StudentSerializer(serializers.ModelSerializer):
    """
    Serializer for the User model, representing a student.
    """
    class Meta:
        model = User
        fields = ["id", "username", "email", "full_name", "is_active"]
        read_only_fields = [
            "id",
            "username",
            "email",
            "full_name",
            "is_active",
        ]


class AddStudentSerializer(serializers.Serializer):
    """
    Serializer for adding a single student by email.
    """
    email = serializers.EmailField()

    def validate_email(self, value) -> Any:
        """
        Validate the provided email address.

        Args:
            value (str): The email address to validate.

        Returns:
            str: The validated email address.

        Raises:
            serializers.ValidationError: If the user does not exist or is already associated with an organization.
        """
        try:
            user = User.objects.get(email=value)
            if user.organization:
                raise serializers.ValidationError(
                    "This user is already associated with an organization."
                )
            return value
        except User.DoesNotExist:
            raise serializers.ValidationError(
                "No user found with this email address."
            )
        except Exception as e:
            # Catch any unexpected error
            raise serializers.ValidationError(f"Unexpected error during email validation: {str(e)}")


class BulkAddStudentSerializer(serializers.Serializer):
    """
    Serializer for adding multiple students by a list of emails.
    """
    emails = serializers.ListField(
        child=serializers.EmailField(),
        min_length=1,
        max_length=100,  # Limit to prevent abuse
    )


class CSVUploadSerializer(serializers.Serializer):
    """
    Serializer for uploading a CSV file containing student emails.
    """
    file = serializers.FileField(
        help_text="CSV file containing student emails. The file should have a header row with 'email' column."
    )


class QuestionPaperSerializer(serializers.ModelSerializer):
    """
    Serializer for the QuestionPaper model.
    """
    class Meta:
        model = QuestionPaper
        fields = ["id", "test", "pdf_file", "answer_key", "uploaded_at"]
        read_only_fields = ["uploaded_at"]


class TestSerializer(serializers.ModelSerializer):
    """
    Serializer for the Test model, including its question paper.
    """
    question_paper = QuestionPaperSerializer(read_only=True)

    class Meta:
        model = Test
        fields = [
            "id",
            "title",
            "description",
            "start_time",
            "duration_minutes",
            "created_at",
            "updated_at",
            "question_paper",
        ]
        read_only_fields = ["created_at", "updated_at"]


class TestAssignmentSerializer(serializers.ModelSerializer):
    """
    Serializer for the TestAssignment model, including test and student details.
    """
    test_details = TestSerializer(source="test", read_only=True)
    student_details = StudentSerializer(source="student", read_only=True)

    class Meta:
        model = TestAssignment
        fields = [
            "id",
            "test",
            "student",
            "test_details",
            "student_details",
            "assigned_at",
            "assigned_at",
            "status",
        ]
        read_only_fields = ["assigned_at", "status", "score"]


class StudentAnswerSerializer(serializers.ModelSerializer):
    """
    Serializer for the StudentAnswer model.
    """
    class Meta:
        model = StudentAnswer
        fields = [
            "id",
            "test",
            "student",
            "question",
            "answer_text",
            "submitted_at",
            "is_evaluated",
            "score",
        ]
        read_only_fields = ["submitted_at", "is_evaluated", "score"]


class OrganizationHierarchyLevelSerializer(serializers.ModelSerializer):
    """
    Serializer for the OrganizationHierarchyLevel model.
    """
    class Meta:
        model = OrganizationHierarchyLevel
        fields = [
            "id",
            "name",
            "description",
            "order",
            "is_active",
            "parent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class HierarchyValueSerializer(serializers.ModelSerializer):
    """
    Serializer for the HierarchyValue model.
    """
    class Meta:
        model = HierarchyValue
        fields = [
            "id",
            "hierarchy_level",
            "value",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class UserHierarchyMembershipSerializer(serializers.ModelSerializer):
    """
    Serializer for the UserHierarchyMembership model.
    """
    class Meta:
        model = UserHierarchyMembership
        fields = [
            "id",
            "user",
            "hierarchy_value",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class UserHierarchyMembershipDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed user hierarchy information, including hierarchy level and value.
    """
    hierarchy_level = serializers.SerializerMethodField()
    value = serializers.SerializerMethodField()

    class Meta:
        model = UserHierarchyMembership
        fields = ["id", "hierarchy_level", "value", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

    def get_hierarchy_level(self, obj) -> Any:
        """
        Get the hierarchy level details for the user hierarchy.

        Args:
            obj (UserHierarchyMembership): The user hierarchy instance.

        Returns:
            dict: The hierarchy level's id and name.
        """
        return {
            "id": obj.hierarchy_value.hierarchy_level.id,
            "name": obj.hierarchy_value.hierarchy_level.name,
        }

    def get_value(self, obj) -> Any:
        """
        Get the value for the user hierarchy.

        Args:
            obj (UserHierarchyMembership): The user hierarchy instance.

        Returns:
            str: The value of the hierarchy.
        """
        return obj.hierarchy_value.value

class AssignmentAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssignmentAttachment
        fields = ['id', 'file', 'uploaded_at']

class SubmissionFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmissionFile
        fields = ['id', 'file', 'uploaded_at']

# --- ADD THESE TWO NEW CLASSES ---

class AssignmentCreateSerializer(serializers.ModelSerializer):
    """
    For serializing data for POST/PUT requests (write-only).
    Accepts primary keys for relationships.
    """
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=HierarchyValue.objects.all(),
        many=True,
        write_only=True
    )

    class Meta:
        model = Assignment
        fields = [
            'id', 'title', 'description', 'due_date', 'points', 'assigned_to'
        ]


class AssignmentDetailSerializer(serializers.ModelSerializer):
    """
    For serializing assignment details for GET requests (read-only).
    Shows nested details for related objects.
    """
    # Note: the field name 'assigned_to' now directly returns the detailed objects
    # because of this nested serializer. We don't need a separate 'assigned_to_details' field.
    assigned_to = HierarchyValueSerializer(many=True, read_only=True)
    attachments = AssignmentAttachmentSerializer(many=True, read_only=True)
    creator = StudentSerializer(read_only=True) 
    submission = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = [
            'id', 'title', 'description', 'due_date', 'points',
            'creator', 'organization', 'assigned_to',
            'attachments', 'created_at', 'submission'
        ]

    def get_submission(self, obj):
        """
        Gets the submission for the currently logged-in user for this specific assignment.
        """
        # The 'request' is available in the serializer's context
        user = self.context['request'].user
        
        # Only try to get submission if the user is authenticated and is a student
        if user.is_authenticated and user.role_org == 'student':
            try:
                submission = Submission.objects.get(assignment=obj, student=user)
                # Use the SubmissionSerializer to format the submission data
                return SubmissionSerializer(submission).data
            except Submission.DoesNotExist:
                # If no submission exists for this user, return null
                return None
        return None



class SubmissionSerializer(serializers.ModelSerializer):
    student_details = StudentSerializer(source='student', read_only=True)
    files = SubmissionFileSerializer(many=True, read_only=True)

    class Meta:
        model = Submission
        fields = [
            'id', 'assignment', 'student', 'student_details', 'status', 'submitted_at',
            'grade', 'feedback', 'files',
            # Added AI fields to make this serializer comprehensive for all outputs
            'ai_grade', 'ai_feedback', 'plagiarism_score'
        ]
        # Your read_only_fields are good, but we can make the entire serializer read-only
        # for safety, as its primary purpose is to display data.
        read_only_fields = fields

# A specific serializer for the manual grading endpoint
class GradeSubmissionSerializer(serializers.Serializer):
    """
    A specific serializer to validate and handle the manual grading of a submission.
    """
    grade = serializers.IntegerField(required=True, min_value=0)
    feedback = serializers.CharField(required=False, allow_blank=True)
    

    def update(self, instance, validated_data):
        """
        This method contains the business logic for grading. It gets called
        by the view when serializer.save() is invoked.
        """
        # Ensure we are working with a Submission instance
        if not isinstance(instance, Submission):
            raise TypeError("The instance must be a Submission object.")

        # Update the instance with validated data from the request
        instance.grade = validated_data.get('grade')
        instance.feedback = validated_data.get('feedback', '') # Use '' as default if not provided
        

        # This is the most important step: update the status to reflect the action
        instance.status = Submission.SubmissionStatus.GRADED

        # Save the changes to the database
        instance.save()
        
        return instance
