from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError

from accounts.models import UserRole
from learning.forms_curation import MaterialUploadForm
from learning.models import Course, Topic

User = get_user_model()

ROLE_COURSE_RELATION = {
    UserRole.STUDENT: "courses_enrolled",
    UserRole.LECTURER: "courses_taught",
    UserRole.TA: "courses_supported",
}


class ManagedUserForm(forms.ModelForm):
    temporary_password = forms.CharField(
        required=False,
        strip=False,
        label="Temporary password (demo only)",
        help_text="Optional. If supplied, this account can sign in immediately without an emailed setup link.",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "placeholder": "Create a temporary password"}),
    )
    confirm_temporary_password = forms.CharField(
        required=False,
        strip=False,
        label="Confirm temporary password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "placeholder": "Repeat the temporary password"}),
    )
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.all().order_by("code"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Courses this person studies, teaches or supports, depending on the role.",
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "student_number", "department", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = UserRole.choices
        if self.instance.pk:
            relation = ROLE_COURSE_RELATION.get(self.instance.role)
            if relation:
                self.fields["courses"].initial = list(getattr(self.instance, relation).values_list("pk", flat=True))

    def clean_username(self):
        value = self.cleaned_data['username']
        if User._base_manager.filter(username=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('This username is already in use. Choose another.')
        return value

    def clean_email(self):
        value = self.cleaned_data['email']
        if User._base_manager.filter(email=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('This email is already in use.')
        return value

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("temporary_password")
        confirmation = cleaned.get("confirm_temporary_password")
        if password or confirmation:
            if password != confirmation:
                self.add_error("confirm_temporary_password", "The temporary passwords do not match.")
            elif password:
                try:
                    password_validation.validate_password(password, self.instance)
                except ValidationError as error:
                    self.add_error("temporary_password", error)
        return cleaned

    def save(self, commit=True):
        is_new = not self.instance.pk
        user = super().save(commit=False)
        temporary_password = self.cleaned_data.get("temporary_password")
        if temporary_password:
            user.set_password(temporary_password)
        elif is_new:
            # The secure default is a short-lived setup link; the optional
            # temporary password exists only for explicit demo/offline use.
            user.set_unusable_password()
        user.save()
        selected = self.cleaned_data.get("courses") or []
        active_relation = ROLE_COURSE_RELATION.get(user.role)
        for relation in ROLE_COURSE_RELATION.values():
            getattr(user, relation).set(selected if relation == active_relation else [])
        return user


class ManagedMaterialForm(MaterialUploadForm):
    """Upload form whose course choices are limited to the courses the actor may manage."""

    def __init__(self, *args, courses=None, **kwargs):
        super().__init__(*args, **kwargs)
        if courses is not None:
            self.fields["course"].queryset = courses
            self.fields["topic"].queryset = Topic.objects.filter(course__in=courses)
