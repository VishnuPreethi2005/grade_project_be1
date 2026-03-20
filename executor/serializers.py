from rest_framework import serializers
from .models import Question, TestCase, Topic, Company

class TestCaseSerializer(serializers.ModelSerializer):

    """
    Serializer for the TestCase model.

    Serializes input data, expected output, whether the test case is a sample,
    and the test type (public/hidden).
    """

    class Meta:
        model = TestCase
        fields = [
            'id',
            'input_data',
            'expected_output',
            'is_sample',
            'test_type',
        ]


class TopicSerializer(serializers.ModelSerializer):

    """
    Serializer for the Topic model.

    Serializes the topic ID and name.
    """
    class Meta:
        model = Topic
        fields = ['id', 'name']


class CompanySerializer(serializers.ModelSerializer):

    """
    Serializer for the Company model.

    Serializes the company ID and name.
    """
    class Meta:
        model = Company
        fields = ['id', 'name']


class QuestionSerializer(serializers.ModelSerializer):

    """
    Serializer for the Question model.

    Includes nested serializers for related test cases, topics, and companies.
    Also adds a human-readable difficulty display.
    """
    test_cases = TestCaseSerializer(many=True, read_only=True)
    topics = TopicSerializer(many=True, read_only=True)
    companies = CompanySerializer(many=True, read_only=True)
    difficulty_display = serializers.CharField(source='get_difficulty_display', read_only=True)

    class Meta:
        model = Question
        fields = [
            'id',
            'title',
            'description',
            'sample_input',
            'sample_output',
            'explanation',
            'constraints',
            'testcase_description',
            'difficulty',
            'difficulty_display',
            'topics',
            'companies',
            'year_asked',
            'test_cases',
        ]


class GenerateQuestionInputSerializer(serializers.Serializer):

    """
    Serializer for validating input data when generating new questions via AI.

    Fields:
        topic (str): The topic name to generate questions for.
        difficulty (str): One of ["Easy", "Medium", "Hard"].
    """
    topic = serializers.CharField()
    difficulty = serializers.ChoiceField(choices=["Easy", "Medium", "Hard"])


from .models import CodeSubmission

class CodeSubmissionSerializer(serializers.ModelSerializer):
    """
    Serializer for the CodeSubmission model.
    """
    class Meta:
        model = CodeSubmission
        fields = [
            'id',
            'user',
            'question',
            'code',
            'language',
            'status',
            'submitted_at',
            'runtime',
            'memory',
        ]
        read_only_fields = ['submitted_at', 'status', 'runtime', 'memory', 'user']
