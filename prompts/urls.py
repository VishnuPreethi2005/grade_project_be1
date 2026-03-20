from .views import (
    get_translation,
    SubscriptionViewset,
    get_transliteration,
    get_entity,
    get_email,
    get_question,
    submit_feedback,
    get_feedback_list,
)
from django.urls import path
from .views import query_with_pdf

"""
    URL patterns for the application.
"""
urlpatterns = [
    # path('', views.async_get_prompt, name="GetPrompt"),
    path("api/translate/", get_translation, name="index_api"),
    path("api/transliterate/", get_transliteration, name="transliterate_api"),
    path("api/entity/", get_entity, name="entity_api"),
    path("api/subscribe/", SubscriptionViewset.as_view()),
    path("api/mail/", get_email, name="email_api"),
    path("api/generateQuestion/", get_question, name="question_api"),
    path("api/feedback/", submit_feedback, name="feedback_api"),
    path("api/feedback/list/", get_feedback_list, name="feedback_list_api"),
    path("api/query-with-pdf/", query_with_pdf, name="query_with_pdf")
]
