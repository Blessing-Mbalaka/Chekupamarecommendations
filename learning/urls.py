from django.urls import path

from .views import (
    assessment_detail_view,
    material_detail_view,
    material_approval_list_view,
    material_approve_view,
    material_approve_selected_view,
    material_file_preview_view,
    material_list_view,
    material_serpapi_transcript_view,
    openalex_pdf_proxy_view,
    quiz_builder_detail_view,
    quiz_builder_view,
    quiz_list_view,
    quiz_question_edit_view,
    quiz_result_view,
    quiz_take_view,
)

app_name = "learning"

urlpatterns = [
    path("materials/", material_list_view, name="material_list"),
    path("materials/approvals/", material_approval_list_view, name="material_approval_list"),
    path("materials/approvals/approve-selected/", material_approve_selected_view, name="material_approve_selected"),
    path("materials/approvals/<int:pk>/approve/", material_approve_view, name="material_approve"),
    path("materials/<int:pk>/", material_detail_view, name="material_detail"),
    path("materials/<int:pk>/preview/", material_file_preview_view, name="material_file_preview"),
    path("materials/<int:pk>/serpapi-transcript/", material_serpapi_transcript_view, name="material_serpapi_transcript"),
    path("materials/openalex/<str:work_id>/pdf/", openalex_pdf_proxy_view, name="openalex_pdf_proxy"),
    path("assessments/<int:pk>/", assessment_detail_view, name="assessment_detail"),
    path("quizzes/", quiz_list_view, name="quiz_list"),
    path("quizzes/builder/", quiz_builder_view, name="quiz_builder"),
    path("quizzes/builder/<int:pk>/", quiz_builder_detail_view, name="quiz_builder_detail"),
    path("quizzes/builder/<int:pk>/questions/<int:question_pk>/", quiz_question_edit_view, name="quiz_question_edit"),
    path("quizzes/<int:pk>/take/", quiz_take_view, name="quiz_take"),
    path("quizzes/results/<int:attempt_pk>/", quiz_result_view, name="quiz_result"),
]
