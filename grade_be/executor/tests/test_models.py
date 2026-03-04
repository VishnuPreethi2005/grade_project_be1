import pytest
from executor.models import Topic, Company, Question, TestCase, SiteSettings


@pytest.mark.django_db
def test_create_topic():
    topic = Topic.objects.create(name="Dynamic Programming")
    assert str(topic) == "Dynamic Programming"


@pytest.mark.django_db
def test_create_company():
    company = Company.objects.create(name="Google")
    assert str(company) == "Google"


@pytest.mark.django_db
def test_create_question():
    question = Question.objects.create(
        title="Two Sum",
        description="Find two numbers that add up to a target",
        sample_input="[2, 7, 11, 15], target = 9",
        sample_output="[0, 1]",
        explanation="2 + 7 = 9",
        constraints="Each input has exactly one solution",
        testcase_description="Basic case",
        difficulty="easy",
    )
    assert str(question) == "Two Sum"
    assert question.custom_id == 1


@pytest.mark.django_db
def test_question_auto_increment_custom_id():
    Question.objects.create(
        title="First Q", description="desc", sample_input="", sample_output="")
    second_question = Question.objects.create(
        title="Second Q", description="desc", sample_input="", sample_output="")
    assert second_question.custom_id == 2


@pytest.mark.django_db
def test_create_testcase():
    question = Question.objects.create(
        title="Add", description="Add two nums", sample_input="1 2", sample_output="3"
    )
    case = TestCase.objects.create(
        question=question,
        input_data={"a": 1, "b": 2},
        expected_output={"result": 3},
        is_sample=True,
        test_type="normal"
    )
    assert "TestCase for Q" in str(case)
    assert str(case).endswith("[normal]")


@pytest.mark.django_db
def test_site_settings_default():
    settings = SiteSettings.objects.create()
    assert settings.log_retention_days == 7
    assert "retention" in str(settings)
