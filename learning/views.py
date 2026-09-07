from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.views.decorators.clickjacking import xframe_options_exempt
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from urllib import parse, request as urllib_request
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError

from recommendations.services.engine import recommend_for_student

from .forms import (
    AssessmentSubmissionForm,
    QuizForm,
    QuizGenerationForm,
    QuizQuestionForm,
    QuizSubmissionForm,
)
from .models import BaselineAssessment, Material, Quiz, QuizAttempt, QuizQuestion
from .services.assessment import grade_assessment
from .services.quizzes import generate_quiz_questions, grade_quiz
from ingestion.services.providers import OPENALEX_API_KEY, OPENALEX_CONTENT_BASE_URL, OPENALEX_EMAIL
from ingestion.services.youtube_research import YouTubeResearchError, store_material_serpapi_transcript


def _safe_fallback_url(raw_url: str, work_id: str) -> str:
    candidate = (raw_url or "").strip()
    if candidate:
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return candidate
    return f"https://openalex.org/{work_id}"


@login_required
def material_list_view(request):
    materials = Material.objects.select_related("course", "topic").filter(is_validated=True)
    recommendations = recommend_for_student(request.user, limit=4)
    return render(
        request,
        "learning/material_list.html",
        {
            "materials": materials,
            "recommendations": recommendations,
            "can_build_quiz": _can_build_quizzes(request.user),
        },
    )


@login_required
def material_detail_view(request, pk):
    material = get_object_or_404(Material.objects.select_related("course", "topic"), pk=pk)
    can_fetch_transcript = _can_build_quizzes(request.user) and material.source_type == Material.SourceType.VIDEO
    return render(
        request,
        "learning/material_detail.html",
        {
            "material": material,
            "can_fetch_transcript": can_fetch_transcript,
            "can_build_quiz": _can_build_quizzes(request.user),
        },
    )


@login_required
def material_serpapi_transcript_view(request, pk):
    material = get_object_or_404(Material.objects.select_related("course"), pk=pk)
    if request.method != "POST" or not _can_build_quizzes(request.user):
        return HttpResponseForbidden("Only teaching staff can fetch and index transcripts.")
    try:
        chunks = store_material_serpapi_transcript(material)
        messages.success(request, f"SerpApi transcript indexed into {chunks} RAG chunks.")
    except YouTubeResearchError as exc:
        messages.error(request, str(exc))
    return redirect("learning:material_detail", pk=material.pk)


@login_required
@xframe_options_exempt
def material_file_preview_view(request, pk):
    material = get_object_or_404(Material, pk=pk, is_validated=True)
    if not material.file or not material.file.name.lower().endswith(".pdf"):
        raise Http404("No previewable PDF is stored for this material.")
    response = FileResponse(
        material.file.open("rb"),
        content_type="application/pdf",
        as_attachment=False,
        filename=material.file.name.rsplit("/", 1)[-1],
    )
    response["Content-Security-Policy"] = "frame-ancestors 'self'"
    return response


@login_required
def assessment_detail_view(request, pk):
    assessment = get_object_or_404(BaselineAssessment.objects.prefetch_related("questions"), pk=pk)
    questions = list(assessment.questions.select_related("topic"))
    if request.method == "POST":
        form = AssessmentSubmissionForm(request.POST, questions=questions)
        if form.is_valid():
            attempt = grade_assessment(assessment, request.user, form.cleaned_data)
            messages.success(
                request,
                f"Assessment submitted. Your current baseline score is {attempt.score}%.",
            )
            return redirect("core:dashboard")
    else:
        form = AssessmentSubmissionForm(questions=questions)

    return render(
        request,
        "learning/assessment_detail.html",
        {"assessment": assessment, "form": form},
    )


def _can_build_quizzes(user):
    return user.is_authenticated and (
        user.is_staff or user.role in {"lecturer", "ta", "admin"}
    )


def _manageable_courses(user):
    from .models import Course

    if user.is_superuser or user.is_staff or user.role == "admin":
        return Course.objects.all()
    return Course.objects.filter(Q(lecturers=user) | Q(teaching_assistants=user)).distinct()


def _can_manage_quiz(user, quiz):
    return _can_build_quizzes(user) and _manageable_courses(user).filter(pk=quiz.course_id).exists()


@login_required
def quiz_list_view(request):
    if _can_build_quizzes(request.user):
        quizzes = Quiz.objects.filter(course__in=_manageable_courses(request.user)).select_related("course")
    else:
        enrolled_ids = request.user.courses_enrolled.values_list("pk", flat=True)
        quizzes = Quiz.objects.filter(is_published=True, course_id__in=enrolled_ids).select_related("course")
    return render(request, "learning/quiz_list.html", {"quizzes": quizzes, "can_build": _can_build_quizzes(request.user)})


@login_required
def quiz_builder_view(request):
    if not _can_build_quizzes(request.user):
        return HttpResponseForbidden("Quiz Builder is available to lecturers, teaching assistants, and administrators.")
    selected_material = Material.objects.filter(pk=request.GET.get("material"), is_validated=True).first()
    initial = {}
    if selected_material and _manageable_courses(request.user).filter(pk=selected_material.course_id).exists():
        initial = {
            "course": selected_material.course,
            "title": f"{selected_material.title} Quiz"[:255],
            "description": f"Knowledge check based on {selected_material.title}.",
        }
    else:
        selected_material = None
    form = QuizForm(request.POST or None, initial=initial)
    form.fields["course"].queryset = _manageable_courses(request.user)
    if request.method == "POST" and form.is_valid():
        quiz = form.save(commit=False)
        quiz.created_by = request.user
        quiz.is_published = False
        quiz.save()
        messages.success(
            request,
            "Quiz created as a draft. Add and review questions before publishing.",
        )
        target = reverse("learning:quiz_builder_detail", args=[quiz.pk]) + "?mode=ai"
        material_id = request.POST.get("source_material")
        if material_id:
            target += f"&material={material_id}"
        return redirect(target)
    quizzes = Quiz.objects.filter(course__in=_manageable_courses(request.user)).select_related("course")
    return render(
        request,
        "learning/quiz_builder.html",
        {"form": form, "quizzes": quizzes, "selected_material": selected_material},
    )


@login_required
def quiz_builder_detail_view(request, pk):
    quiz = get_object_or_404(Quiz.objects.select_related("course"), pk=pk)
    if not _can_manage_quiz(request.user, quiz):
        return HttpResponseForbidden("You cannot edit this quiz.")
    quiz_form = QuizForm(instance=quiz, prefix="quiz")
    quiz_form.fields["course"].queryset = _manageable_courses(request.user)
    mode = request.GET.get("mode", "ai") if request.GET.get("mode") in {"ai", "manual"} else "ai"
    selected_material = Material.objects.filter(
        pk=request.GET.get("material"), course=quiz.course, is_validated=True, content_chunks__isnull=False
    ).first()
    question_form = QuizQuestionForm(quiz=quiz, prefix="question")
    generation_form = QuizGenerationForm(
        quiz=quiz,
        prefix="generate",
        initial={"materials": [selected_material.pk]} if selected_material else None,
    )
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_quiz":
            quiz_form = QuizForm(request.POST, instance=quiz, prefix="quiz")
            quiz_form.fields["course"].queryset = _manageable_courses(request.user)
            if quiz_form.is_valid():
                wants_publish = quiz_form.cleaned_data.get("is_published")
                if wants_publish and not quiz.questions.exists():
                    quiz_form.add_error("is_published", "Add at least one reviewed question before publishing.")
                elif wants_publish and quiz.questions.filter(is_reviewed=False).exists():
                    quiz_form.add_error("is_published", "Review every AI draft before publishing.")
                else:
                    quiz_form.save()
                    messages.success(request, "Quiz settings updated.")
                    return redirect("learning:quiz_builder_detail", pk=quiz.pk)
        elif action == "add_question":
            question_form = QuizQuestionForm(request.POST, quiz=quiz, prefix="question")
            if question_form.is_valid():
                question = question_form.save(commit=False)
                question.is_reviewed = True
                question.save()
                messages.success(request, "Question added.")
                return redirect(reverse("learning:quiz_builder_detail", args=[quiz.pk]) + "?mode=manual")
        elif action == "generate_questions":
            generation_form = QuizGenerationForm(request.POST, quiz=quiz, prefix="generate")
            if generation_form.is_valid():
                created, backend = generate_quiz_questions(
                    quiz,
                    generation_form.cleaned_data["materials"],
                    count=generation_form.cleaned_data["question_count"],
                    question_type=generation_form.cleaned_data["question_type"],
                )
                if created:
                    messages.success(
                        request,
                        f"Created {len(created)} AI draft question(s) using {backend}. Review this draft, edit any field, then save it.",
                    )
                    return redirect("learning:quiz_question_edit", pk=quiz.pk, question_pk=created[0].pk)
                messages.error(request, "No usable question drafts were produced from the selected material.")
        elif action == "delete_question":
            question = get_object_or_404(quiz.questions, pk=request.POST.get("question_id"))
            question.delete()
            messages.success(request, "Question removed.")
            return redirect("learning:quiz_builder_detail", pk=quiz.pk)
    return render(
        request,
        "learning/quiz_builder_detail.html",
        {
            "quiz": quiz,
            "quiz_form": quiz_form,
            "question_form": question_form,
            "generation_form": generation_form,
            "mode": mode,
            "selected_material": selected_material,
        },
    )


@login_required
def quiz_question_edit_view(request, pk, question_pk):
    quiz = get_object_or_404(Quiz, pk=pk)
    if not _can_manage_quiz(request.user, quiz):
        return HttpResponseForbidden("You cannot edit this quiz.")
    question = get_object_or_404(QuizQuestion, pk=question_pk, quiz=quiz)
    form = QuizQuestionForm(request.POST or None, instance=question, quiz=quiz)
    if request.method == "POST" and form.is_valid():
        edited = form.save(commit=False)
        edited.is_reviewed = True
        edited.save()
        messages.success(request, "Question reviewed and saved. It is now ready for publication.")
        return redirect("learning:quiz_builder_detail", pk=quiz.pk)
    return render(request, "learning/quiz_question_edit.html", {"quiz": quiz, "question": question, "form": form})


@login_required
def quiz_take_view(request, pk):
    quiz = get_object_or_404(Quiz.objects.select_related("course").prefetch_related("questions"), pk=pk)
    if not quiz.is_published and not _can_manage_quiz(request.user, quiz):
        raise Http404("Quiz not available.")
    if request.user.role == "student" and not quiz.course.students.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden("This quiz is not assigned to one of your courses.")
    questions = list(quiz.questions.all())
    form = QuizSubmissionForm(request.POST or None, questions=questions)
    if request.method == "POST" and form.is_valid():
        attempt = grade_quiz(quiz, request.user, form.cleaned_data)
        return redirect("learning:quiz_result", attempt_pk=attempt.pk)
    return render(request, "learning/quiz_take.html", {"quiz": quiz, "form": form, "questions": questions})


@login_required
def quiz_result_view(request, attempt_pk):
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related("quiz", "student").prefetch_related("answers__question"), pk=attempt_pk
    )
    if attempt.student_id != request.user.pk and not _can_manage_quiz(request.user, attempt.quiz):
        return HttpResponseForbidden("You cannot view this result.")
    return render(request, "learning/quiz_result.html", {"attempt": attempt})


@login_required
@xframe_options_exempt
def openalex_pdf_proxy_view(request, work_id):
    fallback_url = _safe_fallback_url(request.GET.get("fallback", ""), work_id)
    if not OPENALEX_API_KEY:
        return redirect(fallback_url)
    params = {"api_key": OPENALEX_API_KEY}
    if OPENALEX_EMAIL:
        params["mailto"] = OPENALEX_EMAIL
    pdf_url = f"{OPENALEX_CONTENT_BASE_URL}/works/{work_id}.pdf?" + parse.urlencode(params)
    try:
        upstream_request = urllib_request.Request(pdf_url, headers={"User-Agent": "RecommendationEngine/1.0"})
        with urllib_request.urlopen(upstream_request, timeout=20) as response:
            pdf_bytes = response.read()
            upstream_content_type = response.headers.get("Content-Type", "application/pdf")
        proxy_response = HttpResponse(pdf_bytes, content_type=upstream_content_type)
        proxy_response["Content-Disposition"] = f'inline; filename="{work_id}.pdf"'
        proxy_response["Content-Security-Policy"] = "frame-ancestors 'self'"
        return proxy_response
    except HTTPError as exc:
        return redirect(fallback_url)
    except URLError as exc:
        return redirect(fallback_url)

# Create your views here.
