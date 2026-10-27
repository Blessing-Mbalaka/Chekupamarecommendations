from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django import forms
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import ModuleSettingsForm, StudentProfileForm, UserProfileForm
from .models import UserRole
from .services.profile import get_or_create_student_profile
from analytics_app.models import AnalyticsQuestionnaireResponse


class ActivationAwareAuthenticationForm(AuthenticationForm):
    institution_code = forms.SlugField(
        initial="jbs",
        label="Institution / faculty",
        max_length=60,
        help_text="Johannesburg Business School accounts use jbs.",
    )
    error_messages = {
        **AuthenticationForm.error_messages,
        "inactive": "Your account is deactivated and awaiting activation.",
    }

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if username and password:
            user_model = get_user_model()
            candidate = user_model._default_manager.filter(
                **{user_model.USERNAME_FIELD: username}
            ).first()
            # Only reveal the deactivated state when the password is right.
            if candidate and not candidate.is_active and candidate.check_password(password):
                raise forms.ValidationError(self.error_messages["inactive"], code="inactive")
        result = super().clean()
        user = self.get_user()
        code = self.cleaned_data.get('institution_code', '').lower()
        if user and (user.institution.slug.lower() != code or not user.institution.is_active):
            raise forms.ValidationError('Check your institution code and sign-in details.')
        return result


class DemoLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = ActivationAwareAuthenticationForm

    extra_context = {
        "demo_accounts": [
            {"label": "Student Demo", "username": "demo_student", "password": "Password123!"},
            {"label": "TA Demo", "username": "demo_ta", "password": "Password123!"},
            {"label": "Lecturer Demo", "username": "demo_lecturer", "password": "Password123!"},
        ]
    }

    def get_success_url(self):
        user = self.request.user
        if user.role == UserRole.STUDENT and not user.courses_enrolled.exists():
            return reverse("accounts:module_settings") + "?welcome=1"
        return super().get_success_url()


class SuperuserLoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)


def superuser_login_view(request):
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect("core:curation_portal")

    form = SuperuserLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )
        if user and user.is_superuser:
            login(request, user)
            return redirect("core:curation_portal")
        logout(request)
        messages.error(request, "Only a superuser can access the curation admin console.")
    return render(request, "registration/superuser_login.html", {"form": form})


@login_required
def profile_view(request):
    profile = get_or_create_student_profile(request.user)
    if request.method == "POST":
        user_form = UserProfileForm(request.POST, instance=request.user)
        profile_form = StudentProfileForm(request.POST, instance=profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("accounts:profile")
    else:
        user_form = UserProfileForm(instance=request.user)
        profile_form = StudentProfileForm(instance=profile)

    return render(
        request,
        "accounts/profile.html",
        {
            "user_form": user_form,
            "profile_form": profile_form,
            "analytics_responses": AnalyticsQuestionnaireResponse.objects.filter(user=request.user).select_related("questionnaire"),
        },
    )


@login_required
def module_settings_view(request):
    if request.user.role != UserRole.STUDENT:
        messages.info(request, "Module selection is available to student accounts.")
        return redirect("accounts:profile")

    form = ModuleSettingsForm(request.POST or None, user=request.user)
    available_modules = form.fields["modules"].queryset
    if request.method == "POST" and form.is_valid():
        selected = form.save()
        if selected:
            messages.success(request, "Your module settings have been updated.")
            return redirect("core:dashboard")
        messages.info(
            request,
            "No modules are selected. You can return here after your institution adds them.",
        )
        return redirect("accounts:module_settings")

    return render(
        request,
        "accounts/module_settings.html",
        {
            "form": form,
            "has_available_modules": available_modules.exists(),
            "is_welcome": request.GET.get("welcome") == "1",
        },
    )

# Create your views here.
