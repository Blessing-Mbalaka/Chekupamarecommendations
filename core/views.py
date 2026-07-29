from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from analytics_app.models import AnalyticsEvent
from chatbot.models import ChatSession
from core.services.health import chatbot_health_snapshot
from learning.models import AssessmentAttempt, BaselineAssessment, Course, Material
from recommendations.models import Recommendation


def home_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    return redirect("login")


@login_required
def dashboard_view(request):
    courses = Course.objects.all()[:6]
    materials = Material.objects.select_related("course").filter(is_validated=True)[:6]
    assessments = BaselineAssessment.objects.filter(is_active=True)[:6]
    recommendations = Recommendation.objects.select_related("material").filter(student=request.user)[:5]
    latest_attempt = AssessmentAttempt.objects.filter(student=request.user).order_by("-submitted_at").first()
    session = ChatSession.objects.filter(student=request.user).first()
    analytics_count = AnalyticsEvent.objects.filter(user=request.user).count()

    return render(
        request,
        "core/dashboard.html",
        {
            "courses": courses,
            "materials": materials,
            "assessments": assessments,
            "recommendations": recommendations,
            "latest_attempt": latest_attempt,
            "chat_session": session,
            "analytics_count": analytics_count,
        },
    )


@login_required
def health_view(request):
    if request.user.role == "student" and not request.user.is_staff:
        return HttpResponseForbidden("This health console is only available to staff, lecturers, and teaching assistants.")
    return render(request, "core/health.html", {"health": chatbot_health_snapshot()})
