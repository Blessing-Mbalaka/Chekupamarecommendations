from django.contrib import admin

from ingestion.services.vector_store import index_material

from .models import (
    AssessmentAttempt,
    AssessmentQuestion,
    AttemptAnswer,
    BaselineAssessment,
    Course,
    LecturerPrompt,
    Material,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
    Topic,
)


class TopicInline(admin.TabularInline):
    model = Topic
    extra = 0


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title")
    search_fields = ("code", "title")
    filter_horizontal = ("lecturers", "teaching_assistants", "students")
    inlines = [TopicInline]


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("title", "course")
    search_fields = ("title", "course__code")


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "course",
        "source_origin",
        "source_type",
        "source_provider",
        "publication_year",
        "is_validated",
    )
    list_filter = ("source_origin", "source_type", "source_provider", "is_validated", "course")
    search_fields = (
        "title",
        "description",
        "tags",
        "external_url",
        "original_source_url",
        "source_provider",
        "source_endpoint",
        "source_record_id",
        "authors",
        "publisher",
        "journal_name",
        "doi",
        "isbn",
    )
    readonly_fields = ("created_at", "semantic_text", "embedding")
    fieldsets = (
        ("Library placement", {"fields": ("course", "topic", "title", "description", "tags")} ),
        ("Structured publication", {"fields": (
            "source_type", "publication_year", "authors", "publisher", "journal_name",
            "volume_issue", "doi", "isbn", "youtube_title",
        )}),
        ("Files and links", {"fields": ("file", "external_url", "original_source_url", "source_preview_url")} ),
        ("Provenance", {"fields": (
            "source_origin", "source_provider", "source_endpoint", "source_record_id",
            "source_citation", "uploaded_by", "is_validated", "created_at",
        )}),
        ("Search index", {"classes": ("collapse",), "fields": ("semantic_text", "embedding")} ),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.is_validated and obj.file:
            index_material(obj)


class AssessmentQuestionInline(admin.TabularInline):
    model = AssessmentQuestion
    extra = 0


@admin.register(BaselineAssessment)
class BaselineAssessmentAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "is_active")
    list_filter = ("is_active", "course")
    inlines = [AssessmentQuestionInline]


@admin.register(AssessmentAttempt)
class AssessmentAttemptAdmin(admin.ModelAdmin):
    list_display = ("assessment", "student", "score", "submitted_at")
    list_filter = ("assessment",)


@admin.register(AttemptAnswer)
class AttemptAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "is_correct")


class QuizQuestionInline(admin.StackedInline):
    model = QuizQuestion
    extra = 0


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "is_published", "created_by", "updated_at")
    list_filter = ("course", "is_published")
    search_fields = ("title", "description", "course__code")
    inlines = [QuizQuestionInline]


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("quiz", "student", "score", "max_score", "submitted_at")
    list_filter = ("quiz__course", "quiz")


@admin.register(QuizAnswer)
class QuizAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "is_correct", "awarded_points")
    list_filter = ("is_correct",)


@admin.register(LecturerPrompt)
class LecturerPromptAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "is_active", "created_by")
    list_filter = ("course", "is_active")

# Register your models here.
