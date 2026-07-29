from django.contrib import admin

from .models import AnalyticsEvent


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "user", "path", "duration_seconds", "created_at")
    list_filter = ("event_type",)
    search_fields = ("path", "user__username")

# Register your models here.
