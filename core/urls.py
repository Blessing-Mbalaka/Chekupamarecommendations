from django.contrib.auth.decorators import login_required
from django.urls import path

from . import manage_views as manage
from .views import curation_portal_view, dashboard_view, health_view, home_view

app_name = "core"

urlpatterns = [
    path("", home_view, name="home"),
    path("dashboard/", dashboard_view, name="dashboard"),
    path("ops/health/", health_view, name="health"),
    path("curation/", curation_portal_view, name="curation_portal"),
    path("manage/users/", login_required(manage.user_list_view), name="manage_users"),
    path("manage/users/new/", login_required(manage.user_edit_view), name="manage_user_new"),
    path("manage/users/<int:pk>/", login_required(manage.user_edit_view), name="manage_user_edit"),
    path("manage/users/<int:pk>/toggle-active/", login_required(manage.user_deactivate_view), name="manage_user_toggle"),
    path("manage/users/<int:pk>/invite/", login_required(manage.user_invite_view), name="manage_user_invite"),
    path("manage/materials/", login_required(manage.material_manage_list_view), name="manage_materials"),
    path("manage/materials/new/", login_required(manage.material_manage_edit_view), name="manage_material_new"),
    path("manage/materials/<int:pk>/", login_required(manage.material_manage_edit_view), name="manage_material_edit"),
    path("manage/materials/<int:pk>/delete/", login_required(manage.material_manage_delete_view), name="manage_material_delete"),
    path("manage/materials/<int:pk>/reindex/", login_required(manage.material_manage_reindex_view), name="manage_material_reindex"),
    path("manage/materials/<int:pk>/chunks/", login_required(manage.material_chunks_view), name="manage_material_chunks"),
    path("manage/materials/<int:pk>/chunks/delete/", login_required(manage.chunks_delete_view), name="manage_chunks_delete"),
]
