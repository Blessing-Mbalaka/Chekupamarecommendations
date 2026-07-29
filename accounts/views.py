from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
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
