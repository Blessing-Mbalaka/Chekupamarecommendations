from time import monotonic

from analytics_app.models import AnalyticsEvent
from analytics_app.services.tracking import track_event
from learning.models import Material


class AnalyticsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = monotonic()
        response = self.get_response(request)
        duration_ms = round((monotonic() - started_at) * 1000)
        ignored_prefixes = ("/admin/", "/analytics/track/", "/static/", "/media/")
        if request.user.is_authenticated and not request.path.startswith(ignored_prefixes):
            match = getattr(request, "resolver_match", None)
            route_name = match.view_name if match else ""
            base_metadata = {
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "route_name": route_name,
            }
            track_event(
                user=request.user,
                event_type=AnalyticsEvent.EventType.ENDPOINT,
                path=request.path,
                metadata=base_metadata,
            )

            content_type = response.get("Content-Type", "")
            if request.method == "GET" and response.status_code < 400 and "text/html" in content_type:
                event_type = AnalyticsEvent.EventType.PAGE_VIEW
                material = None
                if route_name == "learning:material_detail":
                    event_type = AnalyticsEvent.EventType.MATERIAL_VIEW
                    material = Material.objects.filter(pk=match.kwargs.get("pk")).first()
                track_event(
                    user=request.user,
                    event_type=event_type,
                    path=request.path,
                    metadata={"route_name": route_name, "status_code": response.status_code},
                    material=material,
                )
        return response
