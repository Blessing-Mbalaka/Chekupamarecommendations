from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import StudentProfile, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = tuple(
        fieldset
        for fieldset in DjangoUserAdmin.fieldsets
        if fieldset[0] != "Personal info"
    ) + (
        (
            "Personal info",
            {"fields": ("first_name", "last_name", "email")},
        ),
        (
            "Academic Profile",
            {
                "fields": (
                    "role",
                    "phone_number",
                    "student_number",
                    "location",
                    "region",
                )
            },
        ),
    )
    list_display = ("username", "email", "role", "student_number", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser")


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "updated_at")
    search_fields = ("user__username", "user__email", "challenges", "identifiers")

# Register your models here.
