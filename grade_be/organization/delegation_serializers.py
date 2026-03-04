from rest_framework import serializers
from .models import TestDelegation, EvaluationAssignment, Test, StudentAnswer
from authentication.models import User


class TestDelegationSerializer(serializers.ModelSerializer):
    """Serializer for TestDelegation model."""
    
    test_title = serializers.CharField(source='test.title', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = TestDelegation
        fields = ['id', 'test', 'test_title', 'user', 'user_email', 'user_name', 'role_type', 'created_at']
        read_only_fields = ['id', 'created_at']


class EvaluationAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for EvaluationAssignment model."""
    
    evaluator_email = serializers.EmailField(source='evaluator.email', read_only=True)
    evaluator_name = serializers.CharField(source='evaluator.username', read_only=True)
    student_email = serializers.EmailField(source='student_answer.student.email', read_only=True)
    test_title = serializers.CharField(source='test.title', read_only=True)
    
    class Meta:
        model = EvaluationAssignment
        fields = [
            'id', 'test', 'test_title', 'student_answer', 
            'evaluator', 'evaluator_email', 'evaluator_name',
            'student_email', 'assigned_at', 'completed_at', 'status'
        ]
        read_only_fields = ['id', 'assigned_at', 'completed_at']


class CreateDelegationSerializer(serializers.Serializer):
    """Serializer for creating a test delegation."""
    
    test_id = serializers.IntegerField(required=True)
    evaluator_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        help_text="List of evaluator user IDs to delegate the test to"
    )
    
    def validate_test_id(self, value):
        """Validate that the test exists and user has access."""
        try:
            test = Test.objects.get(id=value)
            return value
        except Test.DoesNotExist:
            raise serializers.ValidationError("Test not found.")
    
    def validate_evaluator_ids(self, value):
        """Validate that all evaluators exist and have evaluator role."""
        if not value:
            raise serializers.ValidationError("At least one evaluator is required.")
        
        evaluators = User.objects.filter(id__in=value)
        if evaluators.count() != len(value):
            raise serializers.ValidationError("One or more evaluator IDs are invalid.")
        
        # Check if users have evaluator role
        non_evaluators = evaluators.exclude(is_evaluator=True)
        if non_evaluators.exists():
            raise serializers.ValidationError(
                f"Users {list(non_evaluators.values_list('email', flat=True))} are not evaluators."
            )
        
        return value


class DelegationStatsSerializer(serializers.Serializer):
    """Serializer for delegation statistics."""
    
    total_delegations = serializers.IntegerField()
    pending_evaluations = serializers.IntegerField()
    in_progress_evaluations = serializers.IntegerField()
    completed_evaluations = serializers.IntegerField()
    total_evaluators = serializers.IntegerField()
