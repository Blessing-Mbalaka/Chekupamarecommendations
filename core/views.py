import math
from collections import Counter

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.contrib import messages

from analytics_app.models import AnalyticsEvent
from chatbot.models import ChatMessage, ChatSession
from core.services.health import chatbot_health_snapshot
from learning.models import AssessmentAttempt, BaselineAssessment, Course, Material, Topic
from learning.forms_curation import DiscoverySearchForm, MaterialUploadForm, TranscriptUploadForm, YouTubeResearchForm
from learning.services.discovery import (
    REPUTABLE_PROVIDER_NAMES,
    curated_provider_health,
    discover_curated_content,
    import_curated_results,
    import_curated_selection,
)
from recommendations.models import Recommendation
from recommendations.services.presentation import unique_recommendations
from ingestion.models import ContentChunk, ResearchRun, ResearchVideo
from ingestion.services.vector_store import index_material
from ingestion.services.youtube_research import (
    YouTubeResearchError,
    run_youtube_research,
    store_serpapi_transcript,
    store_uploaded_transcript,
)


def home_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    return redirect("login")


@login_required
def dashboard_view(request):
    courses = Course.objects.all()[:6]
    materials = Material.objects.select_related("course", "topic").filter(is_validated=True)[:6]
    assessments = BaselineAssessment.objects.filter(is_active=True)[:6]
    recommendations = unique_recommendations(
        Recommendation.objects.select_related("material", "material__topic").filter(
            student=request.user,
            material__is_validated=True,
        ).order_by("-created_at")[:20]
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
    youtube_form = YouTubeResearchForm(prefix="youtube")
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
                chunks = index_material(material) if material.file else []
                if chunks:
                    messages.success(request, f"Uploaded and indexed {material.title} ({len(chunks)} RAG chunks).")
                else:
                    messages.success(
                        request,
                        f"Stored {material.title}. It is discoverable, but needs an extractable file or transcript before it can ground chat answers.",
                    )
                return redirect("core:curation_portal")
        elif action == "youtube_research":
            youtube_form = YouTubeResearchForm(request.POST, prefix="youtube")
            if youtube_form.is_valid():
                try:
                    run = run_youtube_research(created_by=request.user, **youtube_form.cleaned_data)
                    messages.success(
                        request,
                        f"Collected {run.videos.count()} videos from the title-derived query. Upload transcripts to index them for RAG.",
                    )
                    return redirect(f"{request.path}?research_run={run.pk}#youtube-research")
                except YouTubeResearchError as exc:
                    messages.error(request, str(exc))
                except Exception as exc:
                    messages.error(request, f"YouTube research failed: {exc}")
        elif action == "upload_transcript":
            video = ResearchVideo.objects.select_related("run", "material").filter(pk=request.POST.get("video_id")).first()
            transcript_form = TranscriptUploadForm(request.POST, request.FILES)
            if not video:
                messages.error(request, "That research video no longer exists.")
            elif transcript_form.is_valid():
                uploaded = transcript_form.cleaned_data.get("transcript_file")
                raw_text = transcript_form.cleaned_data.get("transcript_text", "")
                if uploaded:
                    raw_text = uploaded.read().decode("utf-8", errors="replace")
                try:
                    store_uploaded_transcript(video, raw_text)
                    messages.success(request, f"Transcript indexed for {video.title}.")
                except YouTubeResearchError as exc:
                    messages.error(request, str(exc))
                return redirect(f"{request.path}?research_run={video.run_id}#youtube-research")
        elif action == "fetch_serpapi_transcript":
            video = ResearchVideo.objects.select_related("run", "material").filter(pk=request.POST.get("video_id")).first()
            if not video:
                messages.error(request, "That research video no longer exists.")
            else:
                try:
                    store_serpapi_transcript(video)
                    messages.success(request, f"SerpApi transcript fetched and indexed for {video.title}.")
                except YouTubeResearchError as exc:
                    messages.error(request, str(exc))
                return redirect(f"{request.path}?research_run={video.run_id}#youtube-research")
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
    discovery_total = len(discovery_payload.get("results", [])) if discovery_payload else 0
    curated_stats = {
        "validated_materials": Material.objects.filter(is_validated=True).count(),
        "external_materials": Material.objects.filter(source_origin=Material.SourceOrigin.EXTERNAL).count(),
        "internal_materials": Material.objects.filter(source_origin=Material.SourceOrigin.INTERNAL).count(),
        "questions_asked": ChatMessage.objects.filter(sender=ChatMessage.Sender.STUDENT).count(),
        "rag_chunks": ContentChunk.objects.count(),
    }
    if discovery_payload:
        results = discovery_payload.get("results", [])
        curated_stats["discovery_results"] = len(results)
        curated_stats["pdf_ready"] = sum(1 for item in results if item.get("pdf_url"))
        curated_stats["pdf_missing"] = sum(1 for item in results if not item.get("pdf_url"))
    selected_run_id = request.GET.get("research_run")
    latest_research_run = (
        ResearchRun.objects.prefetch_related("themes", "videos__themes")
        .filter(pk=selected_run_id).first()
        if selected_run_id
        else ResearchRun.objects.prefetch_related("themes", "videos__themes").first()
    )
    theme_graph = []
    if latest_research_run:
        for theme in latest_research_run.themes.all():
            theme_graph.append(
                {
                    "id": theme.pk,
                    "label": theme.label,
                    "keywords": ", ".join(theme.keywords),
                    "x": theme.x,
                    "y": theme.y,
                    "radius": theme.radius,
                    "video_count": theme.videos.count(),
                }
            )
    indexed_materials = (
        Material.objects.filter(content_chunks__isnull=False)
        .select_related("course", "topic")
        .prefetch_related("research_videos__themes")
        .distinct()
    )
    library_labels = Counter(label for material in indexed_materials for label in (material.discovered_topics or [material.course.title]))
    library_cluster_graph = []
    for index, (label, material_count) in enumerate(library_labels.most_common(12)):
        angle = (2 * math.pi * index) / max(1, len(library_labels))
        library_cluster_graph.append(
            {
                "label": label,
                "count": material_count,
                "x": 50 + 29 * math.cos(angle),
                "y": 50 + 29 * math.sin(angle),
                "radius": min(35, 18 + material_count * 4),
            }
        )
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
            "curated_stats": curated_stats,
            "discovery_total": discovery_total,
            "youtube_form": youtube_form,
            "latest_research_run": latest_research_run,
            "theme_graph": theme_graph,
            "transcript_form": TranscriptUploadForm(),
            "library_cluster_graph": library_cluster_graph,
        },
    )
