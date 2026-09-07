from django.urls import path

from .views import chat_stream_view, chat_view

app_name = "chatbot"

urlpatterns = [
    path("", chat_view, name="chat"),
    path("stream/", chat_stream_view, name="chat_stream"),
]
