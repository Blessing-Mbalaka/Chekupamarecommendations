from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .forms import ChatMessageForm
from .models import ChatMessage, ChatSession
from .services.chat_engine import generate_bot_response
from recommendations.models import Recommendation
from recommendations.services.presentation import unique_recommendations


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
            "messages": session.messages.all(),
            "form": form,
            "recommendations": unique_recommendations(
                Recommendation.objects.select_related("material")
                .filter(student=request.user)
                .order_by("-created_at")[:20]
            )[:4],
            "latest_bot_message": session.messages.filter(sender=ChatMessage.Sender.BOT).order_by("-created_at").first(),
        },
    )

# Create your views here.
