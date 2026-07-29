from django.conf import settings
from django.db import models
from django.urls import reverse


class Course(models.Model):
    code = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    lecturers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="courses_taught",
    )
    teaching_assistants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="courses_supported",
    )
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="courses_enrolled",
    )

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} - {self.title}"


class Topic(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="topics")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["course__code", "title"]
        unique_together = ("course", "title")

    def __str__(self) -> str:
        return f"{self.course.code}: {self.title}"


class Material(models.Model):
    class SourceOrigin(models.TextChoices):
        INTERNAL = "internal", "Internal Upload"
        EXTERNAL = "external", "External Source"

    class SourceType(models.TextChoices):
        FILE = "file", "Uploaded File"
        WEBSITE = "website", "Website"
        VIDEO = "video", "Video"
        PAPER = "paper", "Academic Paper"
        OTHER = "other", "Other"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="materials")
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name="materials")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    publication_year = models.PositiveIntegerField(null=True, blank=True)
    source_origin = models.CharField(max_length=20, choices=SourceOrigin.choices, default=SourceOrigin.INTERNAL)
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.FILE)
    source_provider = models.CharField(
        max_length=120,
        blank=True,
        help_text="Examples: Uploaded by Lecturer, OpenAlex, Semantic Scholar, YouTube.",
    )
    file = models.FileField(upload_to="materials/", blank=True)
    external_url = models.URLField(blank=True)
    original_source_url = models.URLField(blank=True)
    youtube_title = models.CharField(max_length=255, blank=True)
    tags = models.CharField(max_length=255, blank=True, help_text="Comma-separated tags.")
    source_citation = models.TextField(blank=True)
    semantic_text = models.TextField(blank=True)
    embedding = models.JSONField(default=list, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_materials",
    )
    is_validated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self):
        return reverse("learning:material_detail", args=[self.pk])

    @property
    def effective_source_url(self):
        return self.external_url or self.original_source_url

    @property
    def embed_url(self):
        if self.source_type != self.SourceType.VIDEO or not self.external_url:
            return ""
        if "watch?v=" in self.external_url:
            return self.external_url.replace("watch?v=", "embed/")
        if "youtu.be/" in self.external_url:
            return self.external_url.replace("youtu.be/", "www.youtube.com/embed/")
        return self.external_url


class BaselineAssessment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="baseline_assessments")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["course__code", "title"]

    def __str__(self) -> str:
        return f"{self.course.code}: {self.title}"


class AssessmentQuestion(models.Model):
    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = "mcq", "Multiple Choice"
        SHORT_TEXT = "text", "Short Text"

    assessment = models.ForeignKey(BaselineAssessment, on_delete=models.CASCADE, related_name="questions")
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name="assessment_questions")
    prompt = models.TextField()
    question_type = models.CharField(max_length=10, choices=QuestionType.choices, default=QuestionType.SHORT_TEXT)
    options = models.JSONField(default=list, blank=True)
    correct_option = models.CharField(max_length=255, blank=True)
    expected_keywords = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self) -> str:
        return self.prompt[:80]


class AssessmentAttempt(models.Model):
    assessment = models.ForeignKey(BaselineAssessment, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assessment_attempts")
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self) -> str:
        return f"{self.student} - {self.assessment} ({self.score}%)"


class AttemptAnswer(models.Model):
    attempt = models.ForeignKey(AssessmentAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(AssessmentQuestion, on_delete=models.CASCADE, related_name="answers")
    answer_text = models.TextField(blank=True)
    selected_option = models.CharField(max_length=255, blank=True)
    is_correct = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"Answer to {self.question_id}"


class LecturerPrompt(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lecturer_prompts")
    title = models.CharField(max_length=255)
    prompt_text = models.TextField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="lecturer_prompts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["course__code", "title"]

    def __str__(self) -> str:
        return self.title
