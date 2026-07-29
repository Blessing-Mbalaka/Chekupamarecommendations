from django.urls import path

from .views import assessment_detail_view, material_detail_view, material_list_view

app_name = "learning"

urlpatterns = [
    path("materials/", material_list_view, name="material_list"),
    path("materials/<int:pk>/", material_detail_view, name="material_detail"),
    path("assessments/<int:pk>/", assessment_detail_view, name="assessment_detail"),
]
