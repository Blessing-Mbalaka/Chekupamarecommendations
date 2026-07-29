import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import AnalyticsEvent
from .services.tracking import track_event


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

# Create your views here.
