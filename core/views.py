from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.contrib import messages

from analytics_app.models import AnalyticsEvent
from chatbot.models import ChatSession
from core.services.health import chatbot_health_snapshot
from learning.models import AssessmentAttempt, BaselineAssessment, Course, Material, Topic
from learning.forms_curation import DiscoverySearchForm, MaterialUploadForm
from learning.services.discovery import (
    REPUTABLE_PROVIDER_NAMES,
    curated_provider_health,
    discover_curated_content,
    import_curated_results,
    import_curated_selection,
)
from recommendations.models import Recommendation
from recommendations.services.presentation import unique_recommendations


def home_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    return redirect("login")


@login_required
def dashboard_view(request):
    courses = Course.objects.all()[:6]
    materials = Material.objects.select_related("course").filter(is_validated=True)[:6]
    assessments = BaselineAssessment.objects.filter(is_active=True)[:6]
    recommendations = unique_recommendations(
        Recommendation.objects.select_related("material").filter(student=request.user).order_by("-created_at")[:20]
    )[:5]
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


def _superuser_required(user):
    return user.is_authenticated and user.is_superuser


@user_passes_test(_superuser_required, login_url="superuser_login")
def curation_portal_view(request):
    upload_form = MaterialUploadForm(prefix="upload")
    search_form = DiscoverySearchForm(prefix="discover")
    discovery_payload = request.session.get("curation_last_discovery")
    auto_fetch_ran = request.session.get("curation_autofetch_ran", False)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "upload_material":
            upload_form = MaterialUploadForm(request.POST, request.FILES, prefix="upload")
            if upload_form.is_valid():
                material = upload_form.save(commit=False)
                material.source_origin = Material.SourceOrigin.INTERNAL
                material.source_provider = "Uploaded by Superuser"
                material.source_endpoint = "curation portal upload"
                material.source_record_id = material.source_record_id or f"manual-{material.title[:30]}"
                material.is_validated = True
                material.uploaded_by = request.user
                material.save()
                messages.success(request, f"Uploaded material: {material.title}")
                return redirect("core:curation_portal")
        elif action == "search_discovery":
            search_form = DiscoverySearchForm(request.POST, prefix="discover")
            if search_form.is_valid():
                discovery = discover_curated_content(
                    search_form.cleaned_data["query"],
                    selected_providers=search_form.cleaned_data["providers"],
                    limit_per_provider=search_form.cleaned_data["limit_per_provider"],
                )
                discovery["course_id"] = search_form.cleaned_data["course"].id
                discovery["topic_id"] = search_form.cleaned_data["topic"].id if search_form.cleaned_data["topic"] else None
                request.session["curation_last_discovery"] = discovery
                discovery_payload = discovery
                messages.success(request, "Discovery search completed.")
        elif action == "import_discovery" and discovery_payload:
            course = Course.objects.get(pk=discovery_payload["course_id"])
            topic = Topic.objects.filter(pk=discovery_payload.get("topic_id")).first()
            imported = import_curated_results(
                discovery_payload,
                course=course,
                topic=topic,
                uploaded_by=request.user,
            )
            messages.success(request, f"Imported {len(imported)} materials from discovery results.")
            return redirect("core:curation_portal")
        elif action == "import_single_discovery" and discovery_payload:
            import_key = request.POST.get("import_key", "")
            course = Course.objects.get(pk=discovery_payload["course_id"])
            topic = Topic.objects.filter(pk=discovery_payload.get("topic_id")).first()
            imported = import_curated_selection(
                discovery_payload,
                [import_key],
                course=course,
                topic=topic,
                uploaded_by=request.user,
            )
            if imported:
                messages.success(request, f"Imported {imported[0].title}")
            else:
                messages.error(request, "That result could not be imported.")
            return redirect("core:curation_portal")
        elif action == "session_autofetch":
            if auto_fetch_ran:
                messages.info(request, "Auto-fetch already ran for this session.")
            else:
                search_form = DiscoverySearchForm(request.POST, prefix="discover")
                if search_form.is_valid():
                    discovery = discover_curated_content(
                        search_form.cleaned_data["query"],
                        selected_providers=REPUTABLE_PROVIDER_NAMES,
                        limit_per_provider=search_form.cleaned_data["limit_per_provider"],
                    )
                    imported = import_curated_results(
                        discovery,
                        course=search_form.cleaned_data["course"],
                        topic=search_form.cleaned_data["topic"],
                        uploaded_by=request.user,
                    )
                    request.session["curation_last_discovery"] = discovery
                    request.session["curation_autofetch_ran"] = True
                    discovery_payload = discovery
                    auto_fetch_ran = True
                    messages.success(request, f"Auto-fetch imported {len(imported)} materials for this session.")

    recent_materials = Material.objects.select_related("course", "topic").order_by("-created_at")[:10]
    return render(
        request,
        "core/curation_portal.html",
        {
            "upload_form": upload_form,
            "search_form": search_form,
            "discovery_payload": discovery_payload,
            "recent_materials": recent_materials,
            "provider_health": curated_provider_health(),
            "auto_fetch_ran": auto_fetch_ran,
        },
    )
