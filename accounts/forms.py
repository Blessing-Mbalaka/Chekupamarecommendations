from django import forms

from .models import StudentProfile, User


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "student_number",
            "location",
            "region",
        ]


class StudentProfileForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = ["identifiers", "challenges", "goals"]
        widgets = {
            "identifiers": forms.Textarea(attrs={"rows": 4}),
            "challenges": forms.Textarea(attrs={"rows": 5}),
            "goals": forms.Textarea(attrs={"rows": 4}),
        }
