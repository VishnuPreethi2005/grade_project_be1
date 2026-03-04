import pytest
from executor.serializers import (
    TestCaseSerializer,
    TopicSerializer,
    CompanySerializer,
    QuestionSerializer,
    GenerateQuestionInputSerializer
)
from executor.models import Topic, Company, Question, TestCase


@pytest.mark.django_db
def test_topic_serializer():
    topic = Topic.objects.create(name="Arrays")
    serialized = TopicSerializer(topic)
    assert serialized.data["name"] == "Arrays"


@pytest.mark.django_db
def test_company_serializer():
    company = Company.objects.create(name="Google")
    serialized = CompanySerializer(company)
    assert serialized.data["name"] == "Google"


@pytest.mark.django_db
def test_testcase_serializer():
    question = Question.objects.create(
        title="Add",
        description="Add two numbers",
        sample_input="1 2",
        sample_output="3"
    )
    testcase = TestCase.objects.create(
        question=question,
        input_data={"input": "1 2"},
        expected_output={"output": "3"},
        is_sample=True,
        test_type="normal"
    )
    serialized = TestCaseSerializer(testcase)
    assert serialized.data["is_sample"] is True
    assert serialized.data["test_type"] == "normal"


@pytest.mark.django_db
def test_question_serializer():
    topic = Topic.objects.create(name="Math")
    company = Company.objects.create(name="Amazon")
    question = Question.objects.create(
        title="Multiply",
        description="Multiply two numbers",
        sample_input="2 3",
        sample_output="6",
        difficulty="medium"
    )
    question.topics.add(topic)
    question.companies.add(company)

    serialized = QuestionSerializer(question)
    assert serialized.data["title"] == "Multiply"
    assert serialized.data["difficulty"] == "medium"
    assert serialized.data["difficulty_display"] == "Medium"
    assert serialized.data["topics"][0]["name"] == "Math"
    assert serialized.data["companies"][0]["name"] == "Amazon"


def test_generate_question_input_serializer_valid():
    data = {"topic": "DP", "difficulty": "Easy"}
    serializer = GenerateQuestionInputSerializer(data=data)
    assert serializer.is_valid()


def test_generate_question_input_serializer_invalid():
    data = {"topic": "DP", "difficulty": "Unknown"}
    serializer = GenerateQuestionInputSerializer(data=data)
    assert not serializer.is_valid()
