from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import StudentProfileForm, UserProfileForm
from .services.profile import get_or_create_student_profile


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
