from analytics_app.models import AnalyticsEvent


def track_event(*, user=None, event_type, path="", duration_seconds=0, metadata=None, material=None, chat_session=None):
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    return AnalyticsEvent.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        event_type=event_type,
        path=str(path or "")[:255],
        duration_seconds=max(0, min(int(duration_seconds or 0), 86400)),
        metadata=safe_metadata,
        material=material,
        chat_session=chat_session,
    )
