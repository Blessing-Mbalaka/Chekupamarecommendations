from django.contrib import admin

from .models import ContentChunk, IngestedResource, ResearchRun, ResearchTheme, ResearchVideo


@admin.register(IngestedResource)
class IngestedResourceAdmin(admin.ModelAdmin):
    list_display = ("id", "resource_type", "status", "created_by", "created_at")
    list_filter = ("resource_type", "status")


admin.site.register(ResearchRun)
admin.site.register(ResearchTheme)
admin.site.register(ResearchVideo)
admin.site.register(ContentChunk)

# Register your models here.
