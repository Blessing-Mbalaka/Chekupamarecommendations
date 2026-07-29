from django.conf import settings
from django.db import models

from chatbot.models import ChatSession
from learning.models import Material


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

# Create your models here.
