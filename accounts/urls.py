from django.urls import path

from .views import module_settings_view, profile_view

app_name = "accounts"

urlpatterns = [
    path("profile/", profile_view, name="profile"),
    path("settings/modules/", module_settings_view, name="module_settings"),
]
