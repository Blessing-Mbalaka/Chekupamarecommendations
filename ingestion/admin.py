from django.contrib import admin

from .models import IngestedResource


@admin.register(IngestedResource)
class IngestedResourceAdmin(admin.ModelAdmin):
    list_display = ("id", "resource_type", "status", "created_by", "created_at")
    list_filter = ("resource_type", "status")

# Register your models here.
