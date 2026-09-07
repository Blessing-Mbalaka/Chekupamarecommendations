import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from .forms import ChatMessageForm
from .models import ChatMessage, ChatSession
from .services.chat_engine import generate_bot_response, stream_bot_response


@login_required
def chat_view(request):
    session, _ = ChatSession.objects.get_or_create(student=request.user)
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
            "chat_messages": session.messages.all(),
            "form": form,
        },
    )


@login_required
@require_POST
def chat_stream_view(request):
    form = ChatMessageForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"error": "Enter a message to continue."}, status=400)
    session, _ = ChatSession.objects.get_or_create(student=request.user)
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
