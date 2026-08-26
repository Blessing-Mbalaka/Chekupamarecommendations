from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from accounts.models import User
from learning.models import Material

from analytics_app.models import AnalyticsEvent, AnalyticsQuestion, AnalyticsQuestionnaireResponse


def permitted_analytics_users(user):
    """Return only users whose activity the requesting LMS operator may inspect."""
    if user.is_staff or user.is_superuser or getattr(user, "role", "") == "admin":
        return User.objects.all()
    if getattr(user, "role", "") in {"lecturer", "ta"}:
        return User.objects.filter(
            Q(pk=user.pk)
            | Q(courses_enrolled__lecturers=user)
            | Q(courses_enrolled__teaching_assistants=user)
        ).distinct()
    raise PermissionDenied("Site analytics is available to lecturers and administrators.")


def build_site_analytics_report(*, requesting_user, days=30, selected_user=""):
    users = permitted_analytics_users(requesting_user).order_by("username")
    since = timezone.now() - timezone.timedelta(days=days)
    events = AnalyticsEvent.objects.filter(created_at__gte=since, user__in=users)
    if str(selected_user).isdigit():
        events = events.filter(user_id=selected_user)

    event_counts = {row["event_type"]: row["count"] for row in events.values("event_type").annotate(count=Count("id"))}
    page_events = events.filter(event_type__in=[AnalyticsEvent.EventType.PAGE_VIEW, AnalyticsEvent.EventType.MATERIAL_VIEW])
    top_pages = list(page_events.values("path", "material_id").annotate(count=Count("id")).order_by("-count")[:10])
    top_page_materials = {
        material.pk: material
        for material in Material.objects.filter(
            pk__in=[row["material_id"] for row in top_pages if row["material_id"]]
        ).select_related("topic")
    }
    for row in top_pages:
        material = top_page_materials.get(row["material_id"])
        row["label"] = material.analytics_label if material else row["path"]
    endpoint_rows = list(
        events.filter(event_type=AnalyticsEvent.EventType.ENDPOINT)
        .values("path", "metadata__method", "metadata__status_code")
        .annotate(requests=Count("id"))
        .order_by("-requests")[:12]
    )
    material_rows = list(
        events.filter(material__isnull=False)
        .values("material_id", "material__title", "material__course__code", "material__source_type", "material__topic__title")
        .annotate(
            views=Count("id", filter=Q(event_type=AnalyticsEvent.EventType.MATERIAL_VIEW)),
            clicks=Count("id", filter=Q(event_type__in=[AnalyticsEvent.EventType.CLICK, AnalyticsEvent.EventType.DOWNLOAD])),
            unique_users=Count("user", distinct=True),
        )
        .order_by("-clicks", "-views")[:10]
    )
    material_objects = {
        material.pk: material
        for material in Material.objects.filter(
            pk__in=[row["material_id"] for row in material_rows]
        ).select_related("topic")
    }
    for row in material_rows:
        material = material_objects.get(row["material_id"])
        row["display_name"] = material.analytics_label if material else row["material__title"]
        row["type_label"] = material.get_source_type_display() if material else row["material__source_type"]
    user_rows = list(
        events.exclude(user__isnull=True)
        .values("user_id", "user__username", "user__first_name", "user__last_name")
        .annotate(
            events=Count("id"),
            page_views=Count("id", filter=Q(event_type__in=["page_view", "material_view"])),
            dwell_seconds=Sum("duration_seconds"),
            sessions=Count("metadata__session_id", distinct=True),
            last_seen=Max("created_at"),
        )
        .order_by("-events")[:25]
    )

    daily_map = {}
    for event in events.only("created_at", "event_type"):
        label = timezone.localtime(event.created_at).date().isoformat()
        daily_map.setdefault(label, {"page_views": 0, "clicks": 0, "requests": 0})
        if event.event_type in {"page_view", "material_view"}:
            daily_map[label]["page_views"] += 1
        elif event.event_type == "click":
            daily_map[label]["clicks"] += 1
        elif event.event_type == "endpoint":
            daily_map[label]["requests"] += 1

    click_labels = {}
    for event in events.filter(event_type=AnalyticsEvent.EventType.CLICK).only("metadata"):
        label = event.metadata.get("label") or event.metadata.get("text") or event.metadata.get("element_id") or "Unlabelled"
        label = str(label).strip()[:80] or "Unlabelled"
        click_labels[label] = click_labels.get(label, 0) + 1
    top_clicks = [
        {"label": label, "count": count}
        for label, count in sorted(click_labels.items(), key=lambda item: item[1], reverse=True)[:10]
    ]

    hourly_activity = [0] * 24
    for event in events.exclude(event_type=AnalyticsEvent.EventType.ENDPOINT).only("created_at"):
        hourly_activity[timezone.localtime(event.created_at).hour] += 1

    question_types = {
        (questionnaire_id, key): question_type
        for questionnaire_id, key, question_type in AnalyticsQuestion.objects.filter(
            questionnaire__responses__user__in=users,
            question_type__in=[AnalyticsQuestion.QuestionType.GENDER, AnalyticsQuestion.QuestionType.REGION],
        ).values_list("questionnaire_id", "key", "question_type")
    }
    responses = (
        AnalyticsQuestionnaireResponse.objects.filter(user__in=users, consent_given=True)
        .select_related("user")
        .order_by("user_id", "-updated_at")
    )
    latest_by_user = {}
    for response in responses:
        latest_by_user.setdefault(response.user_id, response)
    demographic_counts = {"gender": {}, "region": {}}
    for response in latest_by_user.values():
        for key, value in response.answers.items():
            category = question_types.get((response.questionnaire_id, key))
            if category not in demographic_counts or not isinstance(value, str) or not value.strip():
                continue
            label = value.strip()[:120]
            demographic_counts[category][label] = demographic_counts[category].get(label, 0) + 1
    demographics_available = len(latest_by_user) >= 3
    if not demographics_available:
        demographic_counts = {"gender": {}, "region": {}}

    return {
        "users": users,
        "selected_user": str(selected_user),
        "days": days,
        "total_events": events.count(),
        "unique_users": events.exclude(user__isnull=True).values("user").distinct().count(),
        "page_view_count": page_events.count(),
        "click_count": event_counts.get(AnalyticsEvent.EventType.CLICK, 0),
        "endpoint_count": event_counts.get(AnalyticsEvent.EventType.ENDPOINT, 0),
        "top_pages": top_pages,
        "top_clicks": top_clicks,
        "endpoint_rows": endpoint_rows,
        "material_rows": material_rows,
        "user_rows": user_rows,
        "demographic_response_count": len(latest_by_user),
        "demographics_available": demographics_available,
        "chart_data": {
            "daily": [{"date": key, **daily_map[key]} for key in sorted(daily_map)],
            "pages": top_pages,
            "clicks": top_clicks,
            "hourly": [{"hour": f"{hour:02d}:00", "count": count} for hour, count in enumerate(hourly_activity)],
            "gender": [{"label": key, "count": value} for key, value in demographic_counts["gender"].items()],
            "regions": [{"label": key, "count": value} for key, value in demographic_counts["region"].items()],
        },
    }
