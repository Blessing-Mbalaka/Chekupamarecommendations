from django.urls import path

from .views import track_event_view

app_name = "analytics_app"

urlpatterns = [
    path("track/", track_event_view, name="track"),
]
