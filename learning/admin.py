from django.contrib import admin

from .models import (
    AssessmentAttempt,
    AssessmentQuestion,
    AttemptAnswer,
    BaselineAssessment,
    Course,
    LecturerPrompt,
    Material,
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
        "source_endpoint",
        "publication_year",
        "is_validated",
    )
    list_filter = ("source_origin", "source_type", "is_validated", "course")
    search_fields = (
        "title",
        "description",
        "tags",
        "external_url",
        "original_source_url",
        "source_provider",
        "source_endpoint",
        "source_record_id",
    )


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


@admin.register(LecturerPrompt)
class LecturerPromptAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "is_active", "created_by")
    list_filter = ("course", "is_active")

# Register your models here.
