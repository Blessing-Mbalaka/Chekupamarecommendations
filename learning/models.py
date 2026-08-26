from django.conf import settings
from django.db import models
from django.urls import reverse
from urllib.parse import parse_qs, urlparse


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
        JOURNAL = "journal", "Journal Article"
        BOOK = "book", "Book"
        BLOG = "blog", "Blog Post"
        OTHER = "other", "Other"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="materials")
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name="materials")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    publication_year = models.PositiveIntegerField(null=True, blank=True)
    authors = models.CharField(max_length=500, blank=True)
    publisher = models.CharField(max_length=255, blank=True)
    journal_name = models.CharField(max_length=255, blank=True)
    volume_issue = models.CharField(max_length=100, blank=True)
    doi = models.CharField(max_length=255, blank=True)
    isbn = models.CharField(max_length=32, blank=True)
    source_origin = models.CharField(max_length=20, choices=SourceOrigin.choices, default=SourceOrigin.INTERNAL)
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.FILE)
    source_provider = models.CharField(
        max_length=120,
        blank=True,
        help_text="Examples: Uploaded by Lecturer, OpenAlex, Semantic Scholar, YouTube.",
    )
    source_endpoint = models.CharField(
        max_length=255,
        blank=True,
        help_text="Exact upstream endpoint or ingest route used to create this material.",
    )
    source_record_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Upstream record identifier such as DOI, OpenAlex ID, Springer identifier, or video ID.",
    )
    file = models.FileField(upload_to="materials/", blank=True)
    external_url = models.URLField(blank=True)
    original_source_url = models.URLField(blank=True)
    source_preview_url = models.CharField(
        max_length=1000,
        blank=True,
        help_text="Direct PDF or same-origin preview URL supplied by the source provider.",
    )
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
        video_id = self.youtube_video_id
        if not video_id:
            return ""
        return f"https://www.youtube-nocookie.com/embed/{video_id}?rel=0"

    @property
    def youtube_video_id(self):
        if self.source_type != self.SourceType.VIDEO or not self.external_url:
            return ""
        parsed = urlparse(self.external_url)
        host = parsed.netloc.lower().split(":")[0]
        if host in {"youtu.be", "www.youtu.be"}:
            return parsed.path.strip("/").split("/")[0]
        if host.endswith("youtube.com"):
            if parsed.path == "/watch":
                return parse_qs(parsed.query).get("v", [""])[0]
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live"}:
                return parts[1]
        return ""

    @property
    def preview_kind(self):
        if self.embed_url:
            return "video"
        if self.document_preview_url:
            return "pdf"
        return "link"

    def _looks_like_document_preview_url(self, candidate: str) -> bool:
        candidate = (candidate or "").strip()
        if not candidate:
            return False
        if candidate.startswith("/") and not candidate.startswith("//"):
            return True
        parsed = urlparse(candidate)
        return parsed.scheme in {"http", "https"} and parsed.path.lower().endswith(".pdf")

    @property
    def document_preview_url(self):
        if self.source_type == self.SourceType.VIDEO:
            return ""
        if self.file and self.file.name.lower().endswith(".pdf"):
            return reverse("learning:material_file_preview", args=[self.pk])
        if self._looks_like_document_preview_url(self.source_preview_url):
            return self.source_preview_url
        if self.source_provider == "OpenAlex" and self.source_record_id:
            work_id = self.source_record_id.rstrip("/").split("/")[-1]
            if work_id.startswith("W"):
                return reverse("learning:openalex_pdf_proxy", args=[work_id])
        if self.effective_source_url and urlparse(self.effective_source_url).path.lower().endswith(".pdf"):
            return self.effective_source_url
        return ""

    @property
    def preview_url(self):
        if self.preview_kind == "video":
            return self.embed_url
        if self.preview_kind == "pdf":
            candidate = self.document_preview_url
            if candidate.startswith("/") and not candidate.startswith("//"):
                return candidate
            if urlparse(candidate).scheme in {"http", "https"}:
                return candidate
        return ""

    @property
    def source_bucket(self):
        return "Additional material" if self.source_origin == self.SourceOrigin.EXTERNAL else "Prescribed material"

    @property
    def content_descriptor(self):
        type_labels = {
            self.SourceType.FILE: "Course file",
            self.SourceType.WEBSITE: "Website",
            self.SourceType.VIDEO: "Video",
            self.SourceType.PAPER: "Academic paper",
            self.SourceType.JOURNAL: "Journal article",
            self.SourceType.BOOK: "Book",
            self.SourceType.BLOG: "Blog post",
            self.SourceType.OTHER: "Learning resource",
        }
        label = type_labels.get(self.source_type, self.get_source_type_display())
        if self.topic_id and self.topic and self.topic.title:
            return f"{label} on {self.topic.title}"
        return f"{label} resource"

    @property
    def analytics_label(self):
        title = (self.youtube_title or self.title or "Untitled resource").strip()
        descriptor = self.content_descriptor
        if title.lower() in descriptor.lower():
            return descriptor
        return f"{descriptor} — {title}"

    @property
    def discovered_topics(self):
        labels = []
        if self.topic:
            labels.append(self.topic.title)
        for research_video in self.research_videos.prefetch_related("themes").all():
            labels.extend(theme.label for theme in research_video.themes.all())
        if not labels and self.tags:
            labels.extend(tag.strip() for tag in self.tags.split(",") if tag.strip())
        return list(dict.fromkeys(labels))


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


class Quiz(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="quizzes")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="quizzes_created"
    )
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["course__code", "title"]

    def __str__(self):
        return f"{self.course.code}: {self.title}"

    def get_absolute_url(self):
        return reverse("learning:quiz_take", args=[self.pk])


class QuizQuestion(models.Model):
    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = "mcq", "Multiple Choice"
        SHORT_TEXT = "text", "Short Text"

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    source_material = models.ForeignKey(
        Material, on_delete=models.SET_NULL, null=True, blank=True, related_name="quiz_questions"
    )
    prompt = models.TextField()
    question_type = models.CharField(max_length=10, choices=QuestionType.choices, default=QuestionType.MULTIPLE_CHOICE)
    options = models.JSONField(default=list, blank=True)
    correct_answer = models.TextField()
    explanation = models.TextField(blank=True)
    points = models.PositiveSmallIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)
    is_ai_generated = models.BooleanField(default=False)
    is_reviewed = models.BooleanField(default=False)
    generation_backend = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.prompt[:80]


class QuizAttempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts")
    score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    max_score = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    @property
    def percentage(self):
        return round((float(self.score) / self.max_score) * 100, 2) if self.max_score else 0


class QuizAnswer(models.Model):
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name="answers")
    response = models.TextField(blank=True)
    is_correct = models.BooleanField(default=False)
    awarded_points = models.DecimalField(max_digits=6, decimal_places=2, default=0)


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
