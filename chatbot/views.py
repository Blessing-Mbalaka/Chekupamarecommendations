import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from accounts.models import UserRole
from learning.models import Course, Material

from .forms import ChatMessageForm
from .models import ChatMessage, ChatSession
from .services.chat_engine import generate_bot_response, stream_bot_response


def _hide_unapproved_materials(messages):
    messages = list(messages)
    material_ids = {
        item.get("material_id")
        for message in messages
        for key in ("sources", "external_suggestions")
        for item in message.metadata.get(key, [])
        if item.get("material_id")
    }
    approved_ids = set(
        Material.objects.filter(pk__in=material_ids, is_validated=True).values_list("pk", flat=True)
    )
    for message in messages:
        metadata = dict(message.metadata)
        for key in ("sources", "external_suggestions"):
            metadata[key] = [
                item for item in metadata.get(key, []) if item.get("material_id") in approved_ids
            ]
        message.metadata = metadata
    return messages


def _available_courses(user):
    if user.role == UserRole.ADMIN:
        return Course.objects.all()
    if user.role == UserRole.LECTURER:
        return user.courses_taught.all()
    if user.role == UserRole.TA:
        return user.courses_supported.all()
    return user.courses_enrolled.all()


def _module_guidance(user, courses, session):
    if not courses:
        if user.role == UserRole.STUDENT:
            return "No modules are available for you yet. Open Module settings to choose from modules added by your institution."
        if user.role == UserRole.TA:
            return "No modules are assigned to you yet. Please ask your lecturer or institution administrator for access."
        if user.role == UserRole.LECTURER:
            return "No modules are assigned to you yet. Please ask your institution administrator for access."
        return "No modules have been created yet. Add a module before starting a module-scoped chat."
    if session and not Material.objects.filter(course=session.course, is_validated=True).exists():
        module_name = session.course.title
        if user.role == UserRole.STUDENT:
            return f"Please wait for your lecturer to upload and validate learning content for {module_name}."
        if user.role == UserRole.TA:
            return f"There is no validated content for {module_name} yet. Please contact the lecturer or institution administrator."
        return f"There is no validated content for {module_name} yet. You can upload and curate material from Manage material."
    return ""


def _resolve_session(request):
    """Return (session, courses). Session is None when a course must be chosen first."""

    user = request.user
    courses = list(_available_courses(user).order_by("title"))
    requested = request.POST.get("course") or request.GET.get("course")
    course = None
    if requested and str(requested).isdigit():
        course = next((c for c in courses if c.pk == int(requested)), None)
    if course is None and len(courses) == 1:
        course = courses[0]
    if course is None:
        # Every conversation is course-bound. This also prevents lecturers and
        # administrators from accidentally searching a cross-course corpus.
        return None, courses
    session = ChatSession.objects.filter(student=user, course=course).first()
    if session is None:
        # Adopt a legacy course-less session instead of orphaning its history.
        # The normal manager intentionally hides unscoped legacy rows. Access
        # only this actor's institution/user row so it can be safely adopted.
        session = ChatSession.all_institutions.filter(
            institution_id=user.institution_id,
            student=user,
            course__isnull=True,
        ).first()
        if session is not None and user.role == UserRole.STUDENT and len(courses) == 1:
            session.course = course
            session.save(update_fields=["course"])
        else:
            session = ChatSession.objects.create(student=user, course=course)
    return session, courses


@login_required
def chat_view(request):
    session, courses = _resolve_session(request)
    if session is None:
        return render(
            request,
            "chatbot/chat.html",
            {
                "session": None,
                "courses": courses,
                "module_guidance": _module_guidance(request.user, courses, None),
                "chat_messages": [],
                "form": ChatMessageForm(),
            },
        )
    if request.method == "POST":
        form = ChatMessageForm(request.POST)
        if form.is_valid():
            message = ChatMessage.objects.create(
                session=session,
                sender=ChatMessage.Sender.STUDENT,
                content=form.cleaned_data["message"],
            )
            bot_payload = generate_bot_response(message)
            ChatMessage.objects.create(
                session=session,
                sender=ChatMessage.Sender.BOT,
                content=bot_payload["text"],
                metadata=bot_payload["metadata"],
            )
            form = ChatMessageForm()
    else:
        form = ChatMessageForm()

    return render(
        request,
        "chatbot/chat.html",
        {
            "session": session,
            "courses": courses,
            "module_guidance": _module_guidance(request.user, courses, session),
            "chat_messages": _hide_unapproved_materials(session.messages.all()),
            "form": form,
        },
    )


@login_required
@require_POST
def chat_stream_view(request):
    form = ChatMessageForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"error": "Enter a message to continue."}, status=400)
    session, _ = _resolve_session(request)
    if session is None:
        return JsonResponse({"error": "Select one of your modules first."}, status=400)
    message = ChatMessage.objects.create(
        session=session,
        sender=ChatMessage.Sender.STUDENT,
        content=form.cleaned_data["message"],
    )

    def event_stream():
        try:
            for event in stream_bot_response(message):
                if event["type"] == "complete":
                    payload = event["payload"]
                    bot_message = ChatMessage.objects.create(
                        session=session,
                        sender=ChatMessage.Sender.BOT,
                        content=payload["text"],
                        metadata=payload["metadata"],
                    )
                    extras_html = render_to_string(
                        "chatbot/_message_extras.html",
                        {"message": bot_message},
                        request=request,
                    )
                    yield json.dumps({"type": "done", "extras_html": extras_html}) + "\n"
                else:
                    yield json.dumps(event) + "\n"
        except Exception:
            yield json.dumps(
                {
                    "type": "error",
                    "text": "The response stream stopped unexpectedly. Please try again.",
                }
            ) + "\n"

    response = StreamingHttpResponse(event_stream(), content_type="application/x-ndjson")
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    return response

# Create your views here.
