from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from recommendations.services.engine import recommend_for_student

from .forms import AssessmentSubmissionForm
from .models import BaselineAssessment, Material
from .services.assessment import grade_assessment


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

# Create your views here.
