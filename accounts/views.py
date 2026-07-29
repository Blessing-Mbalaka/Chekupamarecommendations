from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django import forms
from django.shortcuts import redirect, render

from .forms import StudentProfileForm, UserProfileForm
from .services.profile import get_or_create_student_profile


class DemoLoginView(LoginView):
    template_name = "registration/login.html"

    extra_context = {
        "demo_accounts": [
            {"label": "Student Demo", "username": "demo_student", "password": "Password123!"},
            {"label": "TA Demo", "username": "demo_ta", "password": "Password123!"},
            {"label": "Lecturer Demo", "username": "demo_lecturer", "password": "Password123!"},
        ]
    }


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
        {"user_form": user_form, "profile_form": profile_form},
    )

# Create your views here.
