from django.urls import resolve
from executor import views
from executor.views import QuestionViewSet

def test_run_code_url():
    match = resolve("/api/run_code/")
    assert match.func == views.run_code

def test_generate_questions_url():
    match = resolve("/api/generate_questions/")
    assert match.func == views.generate_questions

def test_grade_code_url():
    match = resolve("/api/grade_code/")
    assert match.func == views.grade_code

def test_question_list_url():
    match = resolve("/api/questions/")
    assert match.func.cls == QuestionViewSet

def test_question_detail_url():
    match = resolve("/api/questions/1/")
    assert match.func.cls == QuestionViewSet
