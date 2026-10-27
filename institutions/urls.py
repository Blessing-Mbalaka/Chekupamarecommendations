from django.urls import path
from . import views
app_name = 'institutions'
urlpatterns = [
    path('register/', views.register_institution, name='register'),
    path('join/', views.register_student, name='join'),
    path('course-management/', views.structure, name='course_management'),
    path('structure/', views.structure, name='structure'),
]
