from analytics_app.models import AnalyticsEvent
from analytics_app.services.tracking import track_event


class AnalyticsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.method == "GET" and request.user.is_authenticated:
            if not request.path.startswith("/admin") and not request.path.startswith("/analytics/track"):
                event_type = AnalyticsEvent.EventType.PAGE_VIEW
                if request.path.startswith("/materials/"):
                    event_type = AnalyticsEvent.EventType.MATERIAL_VIEW
                track_event(user=request.user, event_type=event_type, path=request.path)
        return response
