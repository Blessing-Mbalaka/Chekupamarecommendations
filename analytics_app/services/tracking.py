from analytics_app.models import AnalyticsEvent


def track_event(*, user=None, event_type, path="", duration_seconds=0, metadata=None, material=None, chat_session=None):
    return AnalyticsEvent.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        event_type=event_type,
        path=path,
        duration_seconds=duration_seconds or 0,
        metadata=metadata or {},
        material=material,
        chat_session=chat_session,
    )
