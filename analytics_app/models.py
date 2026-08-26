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
        ENDPOINT = "endpoint", "Endpoint Request"
        FORM_SUBMIT = "form_submit", "Form Submit"
        INPUT_INTERACTION = "input_interaction", "Input Interaction"
        DOWNLOAD = "download", "Download"

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
        indexes = [
            models.Index(fields=["event_type", "created_at"], name="analytics_event_type_time"),
            models.Index(fields=["user", "created_at"], name="analytics_user_time"),
            models.Index(fields=["path", "created_at"], name="analytics_path_time"),
        ]

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
        on_delete=models.SET_NULL,
        null=True,
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


class AnalyticsQuestionnaire(models.Model):
    title = models.CharField(max_length=180)
    purpose = models.TextField(help_text="Explain exactly why this information is being collected and how it will be used.")
    consent_text = models.TextField(
        default=(
            "I voluntarily consent to this information being used for aggregated learning-access analytics. "
            "I understand that I may decline or later withdraw my response without affecting access to learning content."
        )
    )
    retention_days = models.PositiveIntegerField(default=365)
    is_active = models.BooleanField(default=False, help_text="Only a reviewed questionnaire can be shown to users.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_analytics_questionnaires"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_analytics_questionnaires"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_published(self):
        return self.is_active and self.reviewed_at is not None

    def __str__(self):
        return self.title


class AnalyticsQuestion(models.Model):
    class QuestionType(models.TextChoices):
        GENDER = "gender", "Gender (optional demographic)"
        REGION = "region", "Region (coarse geography)"
        SELECT = "select", "Single choice"
        MULTISELECT = "multiselect", "Multiple choice"
        TEXT = "text", "Short text"

    questionnaire = models.ForeignKey(AnalyticsQuestionnaire, on_delete=models.CASCADE, related_name="questions")
    key = models.SlugField(max_length=80, help_text="Stable reporting key, for example gender or province.")
    label = models.CharField(max_length=220)
    help_text = models.CharField(max_length=300, blank=True)
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    options = models.JSONField(default=list, blank=True, help_text="A JSON list of allowed choices for select questions.")
    is_required = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]
        constraints = [models.UniqueConstraint(fields=["questionnaire", "key"], name="unique_analytics_question_key")]

    def __str__(self):
        return self.label

    @property
    def choice_options(self):
        if isinstance(self.options, list) and self.options:
            return [str(option)[:120] for option in self.options]
        if self.question_type == self.QuestionType.GENDER:
            return ["Woman", "Man", "Non-binary", "Self-describe", "Prefer not to say"]
        if self.question_type == self.QuestionType.REGION:
            return [
                "Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo",
                "Mpumalanga", "Northern Cape", "North West", "Western Cape",
                "Outside South Africa", "Prefer not to say",
            ]
        return []


class AnalyticsQuestionnaireResponse(models.Model):
    questionnaire = models.ForeignKey(AnalyticsQuestionnaire, on_delete=models.CASCADE, related_name="responses")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="analytics_questionnaire_responses")
    answers = models.JSONField(default=dict)
    consent_given = models.BooleanField(default=False)
    consented_at = models.DateTimeField()
    consent_version = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [models.UniqueConstraint(fields=["questionnaire", "user"], name="one_analytics_response_per_user")]

    def __str__(self):
        return f"{self.questionnaire} — {self.user}"
