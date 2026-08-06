from django.conf import settings
from django.db import models

from chatbot.models import ChatMessage, ChatSession
from learning.models import Course, Material


class AnalyticsEvent(models.Model):
    class EventType(models.TextChoices):
        PAGE_VIEW = "page_view", "Page View"
        CLICK = "click", "Click"
        MATERIAL_VIEW = "material_view", "Material View"
        DWELL = "dwell", "Dwell"
        CHAT = "chat", "Chat"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    material = models.ForeignKey(Material, on_delete=models.SET_NULL, null=True, blank=True)
    chat_session = models.ForeignKey(ChatSession, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    path = models.CharField(max_length=255, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.event_type} on {self.path}"


class QuestionTheme(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="question_themes")
    label = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    is_model_suggested = models.BooleanField(default=False)
    model_backend = models.CharField(max_length=40, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_question_themes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["course__code", "label"]
        constraints = [
            models.UniqueConstraint(fields=["course", "label"], name="unique_question_theme_per_course")
        ]

    def __str__(self) -> str:
        return f"{self.course.code}: {self.label}"


class AnalyzedQuestion(models.Model):
    message = models.OneToOneField(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name="question_analysis",
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="analyzed_questions")
    text = models.TextField()
    relevance_score = models.FloatField(default=1.0)
    relevance_backend = models.CharField(max_length=40, default="rules")
    classification_reason = models.CharField(max_length=255, blank=True)
    theme = models.ForeignKey(
        QuestionTheme,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
    )
    suggested_theme_label = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.text[:80]
