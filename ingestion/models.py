from django.conf import settings
from django.db import models

from learning.models import Material


class IngestedResource(models.Model):
    class ResourceType(models.TextChoices):
        FILE = "file", "File"
        WEBSITE = "website", "Website"
        YOUTUBE = "youtube", "YouTube"
        PAPER = "paper", "Academic Paper"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    material = models.OneToOneField(
        Material,
        on_delete=models.CASCADE,
        related_name="ingested_resource",
        null=True,
        blank=True,
    )
    resource_type = models.CharField(max_length=20, choices=ResourceType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    source_url = models.URLField(blank=True)
    extracted_text = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ingested_resources",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.resource_type} ({self.status})"

# Create your models here.
