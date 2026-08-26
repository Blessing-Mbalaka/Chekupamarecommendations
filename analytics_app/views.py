import json
import math

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import Resolver404, resolve
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from learning.models import Course, Material

from .forms import QuestionThemeForm, TopicModelForm
from .models import AnalyticsEvent, AnalyticsQuestionnaire, AnalyticsQuestionnaireResponse, AnalyzedQuestion, QuestionTheme
from .services.questions import backfill_relevant_questions, suggest_question_themes
from .services.site_reporting import build_site_analytics_report
from .services.tracking import track_event


THEME_REPORT_SESSION_KEY = "analytics_last_theme_report"


@login_required
@require_POST
def track_event_view(request):
    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)
    event_type = payload.get("event_type", AnalyticsEvent.EventType.CLICK)
    if event_type not in AnalyticsEvent.EventType.values:
        return JsonResponse({"error": "Unsupported analytics event type."}, status=400)
    path = str(payload.get("path", request.path))[:255]
    try:
        duration_seconds = int(payload.get("duration_seconds") or 0)
    except (TypeError, ValueError):
        duration_seconds = 0
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        return JsonResponse({"error": "Metadata must be an object."}, status=400)
    metadata = {str(key)[:80]: value for key, value in list(metadata.items())[:24]}
    if len(json.dumps(metadata)) > 8192:
        return JsonResponse({"error": "Metadata is too large."}, status=400)
    material = None
    href_path = metadata.get("href_path")
    if isinstance(href_path, str) and href_path.startswith("/") and not metadata.get("outbound"):
        try:
            match = resolve(href_path)
            if match.view_name in {
                "learning:material_detail",
                "learning:material_file_preview",
                "learning:material_serpapi_transcript",
            }:
                material = Material.objects.filter(pk=match.kwargs.get("pk")).first()
        except Resolver404:
            pass
    if material:
        metadata["action_label"] = metadata.get("label", "Open material")
        metadata["label"] = material.analytics_label
    track_event(
        user=request.user,
        event_type=event_type,
        path=path,
        duration_seconds=duration_seconds,
        metadata=metadata,
        material=material,
    )
    return JsonResponse({"status": "ok"})


@login_required
@require_POST
def questionnaire_submit_view(request, pk):
    questionnaire = get_object_or_404(
        AnalyticsQuestionnaire.objects.prefetch_related("questions"),
        pk=pk,
        is_active=True,
        reviewed_at__isnull=False,
    )
    if request.POST.get("consent") != "yes":
        return JsonResponse({"error": "Explicit consent is required to submit this questionnaire."}, status=400)

    answers = {}
    errors = {}
    for question in questionnaire.questions.all():
        if question.question_type == question.QuestionType.MULTISELECT:
            value = [item[:200] for item in request.POST.getlist(question.key)[:20]]
        else:
            value = request.POST.get(question.key, "").strip()[:500]
        if question.is_required and not value:
            errors[question.key] = "This question is required."
            continue
        allowed = question.choice_options
        if allowed and value:
            submitted = value if isinstance(value, list) else [value]
            if any(item not in allowed for item in submitted):
                errors[question.key] = "Choose one of the configured options."
                continue
        if value:
            answers[question.key] = value
    if errors:
        return JsonResponse({"error": "Please review the questionnaire.", "fields": errors}, status=400)

    browser_timezone = request.POST.get("browser_timezone", "")[:80]
    if browser_timezone:
        answers["browser_timezone"] = browser_timezone
    AnalyticsQuestionnaireResponse.objects.update_or_create(
        questionnaire=questionnaire,
        user=request.user,
        defaults={
            "answers": answers,
            "consent_given": True,
            "consented_at": timezone.now(),
            "consent_version": questionnaire.updated_at.isoformat(),
        },
    )
    return JsonResponse({"status": "ok"})


@login_required
@require_POST
def questionnaire_withdraw_view(request, pk):
    AnalyticsQuestionnaireResponse.objects.filter(pk=pk, user=request.user).delete()
    messages.success(request, "Your analytics questionnaire response and consent record were deleted.")
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = "/accounts/profile/"
    return redirect(next_url)


@login_required
@require_GET
def site_analytics_view(request):
    days = int(request.GET.get("days", 30)) if request.GET.get("days", "30").isdigit() else 30
    days = days if days in {7, 30, 90} else 30
    selected_user = request.GET.get("user", "")
    context = build_site_analytics_report(
        requesting_user=request.user,
        days=days,
        selected_user=selected_user,
    )
    return render(request, "analytics_app/site_analytics.html", context)


@login_required
@require_GET
def ethics_surveys_view(request):
    if not (request.user.is_staff or request.user.is_superuser or getattr(request.user, "role", "") == "admin"):
        raise PermissionDenied("Ethics and survey configuration is available to administrators only.")
    questionnaires = (
        AnalyticsQuestionnaire.objects.select_related("created_by", "reviewed_by")
        .prefetch_related("questions")
        .annotate(question_count=Count("questions", distinct=True), response_count=Count("responses", distinct=True))
    )
    return render(
        request,
        "analytics_app/ethics_surveys.html",
        {
            "questionnaires": questionnaires,
            "active_questionnaire": questionnaires.filter(is_active=True, reviewed_at__isnull=False).first(),
        },
    )


def manageable_courses(user):
    if user.is_staff or user.is_superuser or getattr(user, "role", "") == "admin":
        return Course.objects.all()
    if getattr(user, "role", "") in {"lecturer", "ta"}:
        return Course.objects.filter(Q(lecturers=user) | Q(teaching_assistants=user)).distinct()
    raise PermissionDenied("Question analytics is available to lecturers and administrators.")


@login_required
def question_analytics_view(request):
    courses = manageable_courses(request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "suggest_themes":
            form = TopicModelForm(request.POST, courses=courses)
            if form.is_valid():
                themes, backend, report = suggest_question_themes(
                    form.cleaned_data["course"],
                    count=form.cleaned_data["theme_count"],
                    model=form.cleaned_data["model"],
                    created_by=request.user,
                )
                request.session[THEME_REPORT_SESSION_KEY] = {
                    **report,
                    "course_id": form.cleaned_data["course"].pk,
                    "course_label": f"{form.cleaned_data['course'].code} · {form.cleaned_data['course'].title}",
                }
                messages.success(request, f"Suggested {len(themes)} themes using {backend}.")
            else:
                messages.error(request, "Choose a valid course and topic-model configuration.")
            return redirect("analytics_app:questions")
        if action == "backfill":
            count = backfill_relevant_questions(courses)
            messages.success(request, f"Added {count} relevant questions from stored conversations.")
            return redirect("analytics_app:questions")
        if action == "assign_theme":
            question = get_object_or_404(AnalyzedQuestion, pk=request.POST.get("question_id"), course__in=courses)
            theme_id = request.POST.get("theme_id")
            theme = get_object_or_404(QuestionTheme, pk=theme_id, course=question.course) if theme_id else None
            question.theme = theme
            question.save(update_fields=["theme"])
            messages.success(request, "Question theme updated.")
            return redirect("analytics_app:questions")

    selected_course = request.GET.get("course", "")
    selected_theme = request.GET.get("theme", "")
    search = request.GET.get("q", "").strip()
    questions = AnalyzedQuestion.objects.filter(course__in=courses).select_related("course", "theme", "message__session__student")
    themes = QuestionTheme.objects.filter(course__in=courses).annotate(question_count=Count("questions"))
    if selected_course.isdigit():
        questions = questions.filter(course_id=selected_course)
        themes = themes.filter(course_id=selected_course)
    if selected_theme == "unassigned":
        questions = questions.filter(theme__isnull=True)
    elif selected_theme.isdigit():
        questions = questions.filter(theme_id=selected_theme)
    if search:
        questions = questions.filter(text__icontains=search)

    theme_list = list(themes)
    total = questions.count()
    for index, theme in enumerate(theme_list):
        angle = (2 * math.pi * index) / max(1, len(theme_list))
        theme.chart_x = 50 + 28 * math.cos(angle)
        theme.chart_y = 50 + 24 * math.sin(angle)
        theme.chart_size = min(34, 15 + theme.question_count * 2)
    all_themes = QuestionTheme.objects.filter(course__in=courses).select_related("course")
    theme_report = request.session.get(THEME_REPORT_SESSION_KEY)
    if theme_report and selected_course.isdigit() and theme_report.get("course_id") != int(selected_course):
        theme_report = None
    keywords_by_label = {
        item.get("label"): ", ".join(item.get("keywords", []))
        for item in (theme_report or {}).get("keywords", [])
        if item.get("label")
    }
    topic_rows = [
        {
            "label": theme.label,
            "question_count": theme.question_count,
            "backend": theme.model_backend or "Manual",
            "keywords": keywords_by_label.get(theme.label, ""),
            "questions": [
                {
                    "text": item.text,
                    "student": str(item.message.session.student) if item.message_id else "Source message removed",
                    "created_at": item.created_at,
                    "confidence": item.relevance_score,
                }
                for item in questions.filter(theme=theme).select_related("message__session__student")[:20]
            ],
        }
        for theme in theme_list
    ]
    model_initial = {"course": selected_course or courses.first()}
    if theme_report:
        model_initial.update(
            {
                "course": theme_report.get("course_id") or model_initial["course"],
                "model": theme_report.get("requested_model", "lda"),
                "theme_count": theme_report.get("requested_count", 5),
            }
        )
    context = {
        "courses": courses,
        "questions": questions[:250],
        "themes": theme_list,
        "all_themes": all_themes,
        "selected_course": selected_course,
        "selected_theme": selected_theme,
        "search": search,
        "total_questions": total,
        "unassigned_count": questions.filter(theme__isnull=True).count(),
        "recent_count": questions.filter(created_at__gte=timezone.now() - timezone.timedelta(days=7)).count(),
        "model_form": TopicModelForm(courses=courses, initial=model_initial),
        "theme_report": theme_report,
        "topic_rows": topic_rows,
    }
    return render(request, "analytics_app/questions.html", context)


@login_required
def question_theme_create_view(request):
    courses = manageable_courses(request.user)
    form = QuestionThemeForm(request.POST or None, courses=courses)
    if request.method == "POST" and form.is_valid():
        theme = form.save(commit=False)
        theme.created_by = request.user
        theme.save()
        messages.success(request, "Theme created.")
        return redirect("analytics_app:questions")
    return render(request, "analytics_app/theme_form.html", {"form": form, "heading": "Create question theme"})


@login_required
def question_theme_edit_view(request, pk):
    courses = manageable_courses(request.user)
    theme = get_object_or_404(QuestionTheme, pk=pk, course__in=courses)
    form = QuestionThemeForm(request.POST or None, instance=theme, courses=courses)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Theme updated.")
        return redirect("analytics_app:questions")
    return render(request, "analytics_app/theme_form.html", {"form": form, "heading": "Edit question theme", "theme": theme})


@login_required
@require_POST
def question_theme_delete_view(request, pk):
    courses = manageable_courses(request.user)
    theme = get_object_or_404(QuestionTheme, pk=pk, course__in=courses)
    theme.delete()
    messages.success(request, "Theme deleted; its questions are now unassigned.")
    return redirect("analytics_app:questions")
