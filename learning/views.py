from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from urllib import parse, request as urllib_request
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError

from recommendations.services.engine import recommend_for_student

from .forms import AssessmentSubmissionForm
from .models import BaselineAssessment, Material
from .services.assessment import grade_assessment
from ingestion.services.providers import OPENALEX_API_KEY, OPENALEX_CONTENT_BASE_URL, OPENALEX_EMAIL


def _safe_fallback_url(raw_url: str, work_id: str) -> str:
    candidate = (raw_url or "").strip()
    if candidate:
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return candidate
    return f"https://openalex.org/{work_id}"


@login_required
def material_list_view(request):
    materials = Material.objects.select_related("course", "topic").all()
    recommendations = recommend_for_student(request.user, limit=4)
    return render(
        request,
        "learning/material_list.html",
        {"materials": materials, "recommendations": recommendations},
    )


@login_required
def material_detail_view(request, pk):
    material = get_object_or_404(Material.objects.select_related("course", "topic"), pk=pk)
    return render(request, "learning/material_detail.html", {"material": material})


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


@login_required
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
        return proxy_response
    except HTTPError as exc:
        return redirect(fallback_url)
    except URLError as exc:
        return redirect(fallback_url)

# Create your views here.
