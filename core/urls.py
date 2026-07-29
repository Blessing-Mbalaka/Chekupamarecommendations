from django.urls import path

from .views import dashboard_view, home_view

app_name = "core"

urlpatterns = [
    path("", home_view, name="home"),
    path("dashboard/", dashboard_view, name="dashboard"),
]
