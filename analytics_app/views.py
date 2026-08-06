import json
import math

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from learning.models import Course

from .forms import QuestionThemeForm, TopicModelForm
from .models import AnalyticsEvent, AnalyzedQuestion, QuestionTheme
from .services.questions import backfill_relevant_questions, suggest_question_themes
from .services.tracking import track_event


THEME_REPORT_SESSION_KEY = "analytics_last_theme_report"


@login_required
@require_POST
def track_event_view(request):
    payload = json.loads(request.body or "{}")
    event_type = payload.get("event_type", AnalyticsEvent.EventType.CLICK)
    path = payload.get("path", request.path)
    duration_seconds = int(payload.get("duration_seconds") or 0)
    metadata = payload.get("metadata") or {}
    track_event(
        user=request.user,
        event_type=event_type,
        path=path,
        duration_seconds=duration_seconds,
        metadata=metadata,
    )
    return JsonResponse({"status": "ok"})


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
