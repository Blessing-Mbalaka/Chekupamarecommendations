from django.conf import settings
from django.db import models

from learning.models import Course, LecturerPrompt


class ChatSession(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_sessions")
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name="chat_sessions")
    title = models.CharField(max_length=255, default="Learning Support Chat")
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.student} - {self.title}"


class ChatMessage(models.Model):
    class Sender(models.TextChoices):
        SYSTEM = "system", "System"
        STUDENT = "student", "Student"
        BOT = "bot", "Bot"

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    sender = models.CharField(max_length=20, choices=Sender.choices)
    content = models.TextField()
    related_prompt = models.ForeignKey(
        LecturerPrompt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_messages",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.sender}: {self.content[:40]}"

# Create your models here.
