from django.contrib import admin
from django import forms

from django.utils import timezone

from .models import (
    AnalyticsEvent,
    AnalyticsQuestion,
    AnalyticsQuestionnaire,
    AnalyticsQuestionnaireResponse,
    AnalyzedQuestion,
    QuestionTheme,
)


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


class AnalyticsQuestionAdminForm(forms.ModelForm):
    options_text = forms.CharField(
        required=False,
        label="Choice options",
        help_text="Enter one option per line. Gender and region questions use privacy-friendly defaults when left blank.",
        widget=forms.Textarea(attrs={"rows": 5, "placeholder": "Option one\nOption two\nPrefer not to say"}),
    )

    class Meta:
        model = AnalyticsQuestion
        exclude = ("options",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and isinstance(self.instance.options, list):
            self.fields["options_text"].initial = "\n".join(str(option) for option in self.instance.options)

    def clean_options_text(self):
        return list(dict.fromkeys(line.strip()[:120] for line in self.cleaned_data["options_text"].splitlines() if line.strip()))[:50]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("question_type") in {
            AnalyticsQuestion.QuestionType.SELECT,
            AnalyticsQuestion.QuestionType.MULTISELECT,
        } and not cleaned.get("options_text"):
            self.add_error("options_text", "Add at least one choice for this question type.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.options = self.cleaned_data.get("options_text", [])
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class AnalyticsQuestionInline(admin.StackedInline):
    model = AnalyticsQuestion
    form = AnalyticsQuestionAdminForm
    extra = 1
    fields = ("order", "key", "label", "help_text", "question_type", "options_text", "is_required")


@admin.register(AnalyticsQuestionnaire)
class AnalyticsQuestionnaireAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "reviewed_at", "retention_days", "response_count", "updated_at")
    list_filter = ("is_active", "reviewed_at")
    readonly_fields = ("created_by", "reviewed_by", "reviewed_at", "created_at", "updated_at")
    inlines = (AnalyticsQuestionInline,)
    actions = ("review_and_publish", "unpublish")

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        if obj.is_active and not obj.reviewed_at:
            obj.is_active = False
            self.message_user(request, "Use ‘Review and publish’ after checking the purpose, consent text, and questions.", level="warning")
        super().save_model(request, obj, form, change)

    @admin.action(description="Review and publish selected questionnaires")
    def review_and_publish(self, request, queryset):
        queryset.update(is_active=False)
        for questionnaire in queryset:
            AnalyticsQuestionnaire.objects.exclude(pk=questionnaire.pk).update(is_active=False)
            questionnaire.is_active = True
            questionnaire.reviewed_by = request.user
            questionnaire.reviewed_at = timezone.now()
            questionnaire.save(update_fields=["is_active", "reviewed_by", "reviewed_at", "updated_at"])

    @admin.action(description="Unpublish selected questionnaires")
    def unpublish(self, request, queryset):
        queryset.update(is_active=False)

    @admin.display(description="Responses")
    def response_count(self, obj):
        return obj.responses.count()


@admin.register(AnalyticsQuestionnaireResponse)
class AnalyticsQuestionnaireResponseAdmin(admin.ModelAdmin):
    list_display = ("questionnaire", "user", "consent_given", "consented_at", "updated_at")
    list_filter = ("questionnaire", "consent_given")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("questionnaire", "user", "answers", "consent_given", "consented_at", "consent_version", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False
