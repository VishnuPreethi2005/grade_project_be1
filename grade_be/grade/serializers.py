"""
Serializers for the grade app.

Defines DRF serializers for grading, question papers, feedback, user authentication, and related entities.
"""
from .models import MainRequest
from .models import Feedback
from rest_framework import serializers
from typing import Any

# Use the custom User model
from .models import AnswerUpload
from authentication.models import User  # Use the custom User model
from .models import (
    SampleQuestionPaper,
    PreviousYearQuestionPaper,
    GeneratedQuestionPaper,
    Questions,
)

# Add these serializers to your existing serializers.py file
from .models import GradingResult, QuestionGrade


class QuestionGradeSerializer(serializers.ModelSerializer):
    """Serializer for detailed question grading"""
    class Meta:
        model = QuestionGrade
        fields = [
            "question_number",
            "allocated_marks",
            "obtained_marks",
            "student_answer",
            "expected_answer",
            "summary",
            "mistakes_identified",
            "final_feedback",
            "concept_analysis",
            "confidence_percentage",
            "confidence_level",
            "diagram_comparison"
        ]


class GradingResultSerializer(serializers.ModelSerializer):
    """Serializer for GradingResult with detailed information"""

    answer_upload_details = serializers.SerializerMethodField()
    result_data = serializers.SerializerMethodField()
    grading_status = serializers.SerializerMethodField()
    question_grades = QuestionGradeSerializer(many=True, read_only=True)  # Add this to include nested question grades


    class Meta:
        model = GradingResult
        fields = [
            "id",
            "answer_upload",
            "answer_upload_details",
            "user_id",
            "total_score",
            "max_possible_score",
            "percentage",
            "questions_count",
            "diagrams_count",
            "grading_processed",
            "grading_error",
            "created_at",
            "graded_at",
            "grading_status",
            "result_data",
            "question_grades",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "graded_at",
            "percentage",
            "answer_upload_details",
            "result_data",
            "grading_status",
        ]

    def get_answer_upload_details(self, obj) -> Any:
        """Get basic answer upload information"""
        if obj.answer_upload:
            return {
                "id": obj.answer_upload.id,
                "question_paper_type": obj.answer_upload.question_paper_type,
                "question_paper_id": obj.answer_upload.question_paper_id,
                "attempt_number": obj.answer_upload.attempt_number,
                "upload_date": obj.answer_upload.upload_date,
            }
        return None

    def get_grading_status(self, obj) -> str:
        """Get human-readable grading status"""
        if obj.grading_processed:
            return "completed"
        elif obj.grading_error:
            return "failed"
        else:
            return "pending"

    def get_result_data(self, obj) -> Any:
        """Get detailed result data if requested"""
        request = self.context.get("request")
        if (
            request
            and request.GET.get("include_details", "").lower() == "true"
        ):
            return obj.get_result_data()
        return None


class GradingResultSummarySerializer(serializers.ModelSerializer):
    """Lighter serializer for listing grading results"""

    grading_status = serializers.SerializerMethodField()

    class Meta:
        model = GradingResult
        fields = [
            "id",
            "user_id",
            "total_score",
            "max_possible_score",
            "percentage",
            "questions_count",
            "diagrams_count",
            "grading_processed",
            "graded_at",
            "created_at",
            "grading_status",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "graded_at",
            "percentage",
            "grading_status",
        ]

    def get_grading_status(self, obj) -> str:
        """Get human-readable grading status"""
        if obj.grading_processed:
            return "completed"
        elif obj.grading_error:
            return "failed"
        else:
            return "pending"


class BaseQuestionPaperSerializer(serializers.ModelSerializer):
    """Base serializer for all question paper types"""

    file_url = serializers.SerializerMethodField()

    def get_file_url(self, obj) -> Any:
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class QuestionsSerializer(BaseQuestionPaperSerializer):
    class Meta:
        model = Questions
        fields = [
            "id",
            "file_url",
            "test_title",
            "board",
            "subject",
            "total_marks",
            "total_questions",
            "upload_date",
            "updated_by",
            "questions",
        ]


class SampleQuestionPaperSerializer(BaseQuestionPaperSerializer):
    class Meta:
        model = SampleQuestionPaper
        fields = [
            "id",
            "file_url",
            "test_title",
            "board",
            "subject",
            "total_marks",
            "total_questions",
            "upload_date",
            "updated_by",
            "questions",
        ]


class PreviousYearQuestionPaperSerializer(serializers.ModelSerializer):
    """Serializer for PreviousYearQuestionPaper - note: file field has been removed"""
    
    class Meta:
        model = PreviousYearQuestionPaper
        fields = [
            "id",
            "test_title",
            "board",
            "subject",
            "total_marks",
            "total_questions",
            "upload_date",
            "updated_by",
            "questions",
            "year",
            "qp_code",
            "set_number",
        ]


class GeneratedQuestionPaperSerializer(BaseQuestionPaperSerializer):
    class Meta:
        model = GeneratedQuestionPaper
        fields = [
            "id",
            "file_url",
            "test_title",
            "board",
            "subject",
            "total_marks",
            "total_questions",
            "upload_date",
            "updated_by",
            "questions",
        ]


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email"]

    def validate_email(self, value) -> Any:
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found.")
        except Exception as e:
            raise serializers.ValidationError(f"Unexpected error during email validation: {str(e)}")
        return user  # Return the user object


class GradeMasterSignupSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username", "password", "email", "role"]  # Add role here
        extra_kwargs = {"password": {"write_only": True}}

    def create(self, validated_data) -> Any:
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            role=validated_data["role"],  # Include role in user creation
        )
        return user


class GradeMasterLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, data) -> Any:
        email = data.get("email")
        password = data.get("password")
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email or password.")
        except Exception as e:
            raise serializers.ValidationError(f"Unexpected error during login: {str(e)}")
        if not user.check_password(password):
            raise serializers.ValidationError("Invalid email or password.")
        return {
            "user": user,
            "role": user.role,  # Return the role directly from the user model
        }


class AnswerUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerUpload
        fields = ["file", "feedback", "correction"]


class AnswerUploadSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(write_only=True)

    class Meta:
        model = AnswerUpload
        fields = ["file", "feedback", "correction", "email"]

    def create(self, validated_data) -> Any:
        # Get the email from validated data
        email = validated_data.pop("email")
        try:
            # Retrieve user based on email
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found.")
        except Exception as e:
            # Catch any unexpected error
            raise serializers.ValidationError(f"Unexpected error retrieving user: {str(e)}")
        try:
            answer_upload = AnswerUpload.objects.create(
                user=user, **validated_data
            )
        except Exception as e:
            raise serializers.ValidationError(f"Error creating AnswerUpload: {str(e)}")
        return answer_upload


class FeedbackSerializer(serializers.ModelSerializer):
    marks_obtained = serializers.SerializerMethodField()

    def get_marks_obtained(self, obj):
        # Return 0 if allocated marks are 0 or obtained marks are unassigned
        if obj.marks_out_of == 0:
            return 0.0 if isinstance(obj.marks_obtained, float) else 0
        return obj.marks_obtained or 0

    class Meta:
        model = Feedback
        fields = [
            "question_number",
            "marks_obtained",
            "marks_out_of",
            "feedback",
            "complexity",
        ]


class MainRequestSerializer(serializers.ModelSerializer):
    email = serializers.SerializerMethodField()

    class Meta:
        model = MainRequest
        fields = [
            "id",
            "role",
            "board",
            "subject",
            "resume",
            "email",
        ]  # Include 'email' in fields

    def get_email(self, obj) -> Any:
        return (
            obj.user.email if obj.user else None
        )  # Safeguard in case user is None


# from rest_framework import serializers
# from .models import MainRequest, Evaluator
# from authentication.models import User

# class UserSerializer(serializers.ModelSerializer):
#     """Serializer for User profile details."""
#     class Meta:
#         model = User
#         fields = ['id', 'full_name', 'country', 'state', 'city', 'address_line1', 'address_line2', 'phone_number']

# class EvaluatorSerializer(serializers.ModelSerializer):
#     """Serializer for Evaluator details, including related User."""
#     user = UserSerializer()  # Nested user serializer

#     class Meta:
#         model = Evaluator
#         fields = ['id', 'user', 'rating', 'resume', 'languages', 'subjects', 'boards', 'created_at', 'updated_at']

# class MainRequestSerializer(serializers.ModelSerializer):
#     """Serializer for MainRequest, with optional Evaluator details."""
#     evaluator_details = EvaluatorSerializer(source='evaluator', read_only=True)

#     class Meta:
#         model = MainRequest
#         fields = ['id', 'role', 'resume', 'board', 'subject', 'created_at', 'updated_at', 'evaluator_details']
