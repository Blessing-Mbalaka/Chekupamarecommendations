from django.contrib import admin

from .models import AnalyticsEvent, AnalyzedQuestion, QuestionTheme


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "user", "path", "duration_seconds", "created_at")
    list_filter = ("event_type",)
    search_fields = ("path", "user__username")


@admin.register(QuestionTheme)
class QuestionThemeAdmin(admin.ModelAdmin):
    list_display = ("label", "course", "is_model_suggested", "model_backend", "updated_at")
    list_filter = ("course", "is_model_suggested", "model_backend")
    search_fields = ("label", "description")


@admin.register(AnalyzedQuestion)
class AnalyzedQuestionAdmin(admin.ModelAdmin):
    list_display = ("short_text", "course", "theme", "relevance_score", "created_at")
    list_filter = ("course", "theme", "relevance_backend")
    search_fields = ("text", "classification_reason")

    @admin.display(description="Question")
    def short_text(self, obj):
        return obj.text[:80]
