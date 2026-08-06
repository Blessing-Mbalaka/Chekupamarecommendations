from django.urls import path

from .views import (
    question_analytics_view,
    question_theme_create_view,
    question_theme_delete_view,
    question_theme_edit_view,
    track_event_view,
)

app_name = "analytics_app"

urlpatterns = [
    path("track/", track_event_view, name="track"),
    path("questions/", question_analytics_view, name="questions"),
    path("questions/themes/new/", question_theme_create_view, name="theme_create"),
    path("questions/themes/<int:pk>/edit/", question_theme_edit_view, name="theme_edit"),
    path("questions/themes/<int:pk>/delete/", question_theme_delete_view, name="theme_delete"),
]
