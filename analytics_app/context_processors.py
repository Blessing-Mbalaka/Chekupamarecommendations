from .models import AnalyticsQuestionnaire


def analytics_questionnaire(request):
    if (
        not request.user.is_authenticated
        or request.user.is_staff
        or request.user.is_superuser
        or getattr(request.user, "role", "") != "student"
    ):
        return {}
    questionnaire = (
        AnalyticsQuestionnaire.objects.filter(is_active=True, reviewed_at__isnull=False)
        .prefetch_related("questions")
        .first()
    )
    if not questionnaire or questionnaire.responses.filter(user=request.user).exists():
        return {"analytics_questionnaire": None}
    return {"analytics_questionnaire": questionnaire}
