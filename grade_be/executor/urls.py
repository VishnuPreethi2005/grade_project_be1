#executor - urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from executor.views import run_code, generate_questions, QuestionViewSet, grade_code, CodeSubmissionViewSet

# Router registration
router = DefaultRouter()
router.register(r'questions', QuestionViewSet, basename='question')
router.register(r'submissions', CodeSubmissionViewSet, basename='submission')

urlpatterns = [
    path('run_code/', run_code, name='run_code'),
    path('generate_questions/', generate_questions, name='generate_questions'),
    path('grade_code/', grade_code, name='grade_code'),
    path('', include(router.urls)),  # This exposes /api/questions/ correctly
]
