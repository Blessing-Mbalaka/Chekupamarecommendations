from django.urls import path

from .views import (
    ethics_surveys_view,
    question_analytics_view,
    question_theme_create_view,
    question_theme_delete_view,
    question_theme_edit_view,
    questionnaire_submit_view,
    questionnaire_withdraw_view,
    site_analytics_view,
    track_event_view,
)

app_name = "analytics_app"

urlpatterns = [
    path("track/", track_event_view, name="track"),
    path("site/", site_analytics_view, name="site"),
    path("ethics/", ethics_surveys_view, name="ethics"),
    path("questionnaires/<int:pk>/submit/", questionnaire_submit_view, name="questionnaire_submit"),
    path("questionnaires/responses/<int:pk>/withdraw/", questionnaire_withdraw_view, name="questionnaire_withdraw"),
    path("questions/", question_analytics_view, name="questions"),
    path("questions/themes/new/", question_theme_create_view, name="theme_create"),
    path("questions/themes/<int:pk>/edit/", question_theme_edit_view, name="theme_edit"),
    path("questions/themes/<int:pk>/delete/", question_theme_delete_view, name="theme_delete"),
]
