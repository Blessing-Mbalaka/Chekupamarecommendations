from django import forms

from learning.models import Course

from .models import StudentProfile, User


class UserProfileForm(forms.ModelForm):
    def clean_email(self):
        value = self.cleaned_data['email']
        if self._meta.model._base_manager.filter(email=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('This email is already in use.')
        return value

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


class ModuleSettingsForm(forms.Form):
    modules = forms.ModelMultipleChoiceField(
        queryset=Course.all_institutions.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Your modules",
        help_text="Choose every module you are taking. You can update this list later.",
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["modules"].queryset = Course.all_institutions.filter(
            institution_id=user.institution_id
        ).order_by("code", "title")
        if not self.is_bound:
            self.initial["modules"] = Course.all_institutions.filter(
                institution_id=user.institution_id,
                students=user,
            )

    def save(self):
        selected = self.cleaned_data["modules"]
        # The form queryset is institution-bound, so an ID from another
        # institution is rejected before this relation is updated.
        self.user.courses_enrolled.set(selected)
        return selected
