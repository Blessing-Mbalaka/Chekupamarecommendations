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


class ResearchRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETE = "complete", "Complete"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"

    course = models.ForeignKey("learning.Course", on_delete=models.CASCADE, related_name="research_runs")
    topic = models.ForeignKey(
        "learning.Topic", on_delete=models.SET_NULL, null=True, blank=True, related_name="research_runs"
    )
    seed_url = models.URLField()
    seed_video_id = models.CharField(max_length=32)
    seed_title = models.CharField(max_length=500)
    research_query = models.CharField(max_length=500)
    requested_video_count = models.PositiveSmallIntegerField(default=10)
    topic_model = models.CharField(max_length=30, default="lda")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="research_runs"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ResearchTheme(models.Model):
    run = models.ForeignKey(ResearchRun, on_delete=models.CASCADE, related_name="themes")
    label = models.CharField(max_length=160)
    keywords = models.JSONField(default=list)
    description = models.TextField(blank=True)
    x = models.FloatField(default=0)
    y = models.FloatField(default=0)
    radius = models.FloatField(default=28)

    class Meta:
        ordering = ["pk"]


class ResearchVideo(models.Model):
    run = models.ForeignKey(ResearchRun, on_delete=models.CASCADE, related_name="videos")
    material = models.ForeignKey(
        Material, on_delete=models.CASCADE, related_name="research_videos", null=True, blank=True
    )
    youtube_id = models.CharField(max_length=32)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    channel_title = models.CharField(max_length=255, blank=True)
    published_at = models.CharField(max_length=50, blank=True)
    duration = models.CharField(max_length=32, blank=True)
    thumbnail_url = models.URLField(blank=True)
    transcript = models.TextField(blank=True)
    transcript_status = models.CharField(max_length=40, default="missing")
    metadata = models.JSONField(default=dict, blank=True)
    themes = models.ManyToManyField(ResearchTheme, through="ResearchVideoTheme", related_name="videos")

    class Meta:
        ordering = ["pk"]
        unique_together = ("run", "youtube_id")


class ResearchVideoTheme(models.Model):
    video = models.ForeignKey(ResearchVideo, on_delete=models.CASCADE)
    theme = models.ForeignKey(ResearchTheme, on_delete=models.CASCADE)
    weight = models.FloatField(default=0)

    class Meta:
        unique_together = ("video", "theme")


class ContentChunk(models.Model):
    """A persisted RAG unit. Chat retrieval is intentionally limited to this table."""

    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="content_chunks")
    research_video = models.ForeignKey(
        ResearchVideo, on_delete=models.CASCADE, related_name="content_chunks", null=True, blank=True
    )
    ordinal = models.PositiveIntegerField(default=0)
    text = models.TextField()
    embedding = models.JSONField(default=list, blank=True)
    embedding_backend = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["material_id", "ordinal"]
        unique_together = ("material", "ordinal")

# Create your models here.
