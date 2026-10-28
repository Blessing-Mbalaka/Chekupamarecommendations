from django.urls import path
from . import views
app_name = 'institutions'
urlpatterns = [
    path('register/', views.register_institution, name='register'),
    path('join/', views.register_student, name='join'),
    path('join-lecturer/', views.register_lecturer, name='join_lecturer'),
    path('course-management/', views.structure, name='course_management'),
    path('topic-management/', views.topic_management, name='topic_management'),
    path('structure/', views.structure, name='structure'),
]
