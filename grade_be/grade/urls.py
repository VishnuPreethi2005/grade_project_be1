"""
URL configuration for the grade app.

Defines all API endpoints for grading, question paper management, feedback, user authentication, and related features.
"""
from django.urls import path
from django.conf.urls.static import static
from django.conf import settings
from .views import (
    signup_view,
    login_view,
    get_question_for_evaluator,
    save_feedback,
    get_question_feedback,
    get_upload_history,
    get_my_corrections,
    save_feedback_for,
    delete_feedback,
    get_feedback,
    get_students,
)
from .views import (
    get_requests,
    handle_request,
    get_student_requests,
    get_notifications,
    send_mentor_request,
    get_accepted_students,
    update_notification,
    add_mentor_student_relationship,
    create_main_request,
    get_main_requests,
    check_submission,
    accept_main_request,
    save_question,
    get_questions,
)
from .views import (
    assign_answers_view,
    reassign_expired_answers,
    evaluator_dashboard,
    check_user_permission,
    assign_answer_to_evaluator,
    bulk_upload_previous_year_question_papers,
)
from django.urls import path
from . import views
from .views import get_evaluators, get_unassigned_answers

urlpatterns = [
    path("signup/", signup_view, name="grade_signup"),
    path("login/", login_view, name="grade_login"),
    # path(
    #     "upload/sample/",
    #     views.upload_sample_question_paper,
    #     name="upload_sample_question_paper",
    # ),
    path("upload/", views.upload_questions, name="upload_questions"),
    path(
        "upload/previousyear/",
        views.upload_previous_year_question_paper,
        name="upload_previous_year_question_paper",
    ),
    path(
        "upload/previousyear/bulk/",
        views.bulk_upload_previous_year_question_papers,
        name="bulk_upload_previous_year_question_papers",
    ),
    path(
        "upload/generated/",
        views.upload_generated_question_paper,
        name="upload_generated_question_paper",
    ),
    # GET endpoints for retrieving question papers with answered/available
    # status
    #path(
        #"sample/",
        #views.get_sample_question_papers,
        #name="get_sample_question_papers",
    #),
    path(
        "previous-year/",
        views.get_previous_year_question_papers,
        name="get_previous_year_question_papers",
    ),
    path(
        "generated/",
        views.get_generated_question_papers,
        name="get_generated_question_papers",
    ),
    path(
        "question-papers/",
        views.get_all_question_papers,
        name="get_all_question_papers",
    ),
    path("qp_uploader/", views.get_questions, name="get_questions"),
    # path('ocr/process/', views.start_ocr_processing, name='start_ocr_processing'),
    # Check status of OCR processing job
    # path('ocr/status/<str:job_id>/', views.check_ocr_status, name='check_ocr_status'),
    # List available files in input directory
    # path('ocr/files/', views.list_input_files, name='list_input_files'),
    path(
        "grade-answer/<int:answer_id>/",
        views.grade_answer,
        name="grade_answer",
    ),
    path(
        "grading-result/<int:answer_id>/",
        views.get_grading_result,
        name="get_grading_result",
    ),
    path(
        "user-grading-results/<str:user_id>/",
        views.get_user_grading_results,
        name="get_user_grading_results",
    ),
    path(
        "delete-grading/<int:grading_id>/",
        views.delete_grading_result,
        name="delete_grading_result",
    ),
    path(
        "grading-report/<int:grading_id>/",
        views.download_grading_report,
        name="download_grading_report",
    ),
    path(
        "answer-ocr-data/<int:answer_id>/",
        views.get_answer_ocr_data,
        name="get_answer_ocr_data",
    ),
    path(
        "answer-ocr-data/<int:answer_id>/update/",
        views.update_answer_ocr_data,
        name="update_answer_ocr_data",
    ),
    path(
        "answer-upload/<int:answer_id>/upload-asset/",
        views.upload_answer_asset,
        name="upload_answer_asset",
    ),
    path(
        "check-status/<int:answer_upload_id>/",
        views.check_processing_status,
        name="check_processing_status",
    ),
    # Cleanup job status (optional)
    # path('api/ocr/cleanup/<str:job_id>/', views.cleanup_job, name='cleanup_job'),
    # GET endpoints for directly accessing specific files
    # path('sample/<int:file_id>/', views.get_sample_question_paper_file, name='get_sample_question_paper_file'),
    # path('previous-year/<int:file_id>/', views.get_previous_year_question_paper_file, name='get_previous_year_question_paper_file'),
    # path('generated/<int:file_id>/', views.get_generated_question_paper_file, name='get_generated_question_paper_file'),
    # Answer upload endpoint
    path("upload-answer/", views.upload_answer, name="upload_answer"),
    # Test attempts history endpoint
    path(
        "test-attempts/<str:question_paper_type>/<int:question_paper_id>/",
        views.get_test_attempts,
        name="get_test_attempts",
    ),
    path(
        "evaluator_question/",
        get_question_for_evaluator,
        name="evaluator-question-list",
    ),
    path("save_feedback/", save_feedback, name="save_feedback"),
    path(
        "question-feedback/<int:feedback_id>/",
        get_question_feedback,
        name="get-question-feedback",
    ),
    path(
        "uploadHistory/<str:email>/",
        get_upload_history,
        name="upload-history-email",
    ),
    path(
        "myCorrections/<str:evaluator_email>/",
        get_my_corrections,
        name="my_corrections",
    ),
    path("save_feedback_for/", save_feedback_for, name="save_feedback"),
    path(
        "delete_feedback/<int:answer_upload_id>/",
        delete_feedback,
        name="delete_feedback",
    ),
    path("get_feedback/<int:answer_id>/", get_feedback, name="get_feedback"),
    path("get-students/", get_students, name="get-students"),
    # mentor request
    path("send-request/", send_mentor_request, name="send-request"),
    path("get-requests/", get_requests, name="get-requests"),
    path("handle-request/", handle_request, name="handle-request"),
    path(
        "mentor-requests/<int:student_id>/",
        get_student_requests,
        name="get_student_requests",
    ),
    path("notifications/", get_notifications, name="notifications"),
    path(
        "get-accepted-students/",
        get_accepted_students,
        name="get_accepted_students",
    ),
    path(
        "notifications/<int:notification_id>/update/",
        update_notification,
        name="update_notification",
    ),
    path(
        "mentor-student/",
        add_mentor_student_relationship,
        name="add_mentor_student_relationship",
    ),
    path(
        "mainrequest/", create_main_request, name="request_from_eval_qpupload"
    ),
    path("main-requests/", get_main_requests, name="get_main_requests"),
    path("checksubmission/", check_submission, name="check_sub"),
    path(
        "accept_main_request/<int:id>/accept/",
        accept_main_request,
        name="accept_main_request",
    ),
    path("questions/", save_question, name="save_question"),
    path("api/questions/list/", get_questions, name="get_questions"),
    path("assign-answers/", assign_answers_view, name="assign-answers"),
    path(
        "reassign-expired/", reassign_expired_answers, name="reassign-expired"
    ),
    path(
        "evaluator-dashboard/", evaluator_dashboard, name="evaluator-dashboard"
    ),
    path(
        "checkpermission/", check_user_permission, name="check-user-permission"
    ),
    path(
        "assign-answer-to-evaluator/",
        assign_answer_to_evaluator,
        name="assign-answer-to-evaluator",
    ),
    # OCR Processing URLs
    # path('ocr/answer/<str:job_id>/<str:roll_number>/', views.get_processed_answer, name='get_processed_answer'),
    # path('ocr/results/answer/<int:answer_id>/', views.get_ocr_results_by_answer_id, name='get_ocr_results_by_answer_id'),
    path("get-evaluators/", get_evaluators, name="get-evaluators"),
    path(
        "unassigned-answers/",
        get_unassigned_answers,
        name="unassigned-answers",
    ),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL, document_root=settings.MEDIA_ROOT
    )
