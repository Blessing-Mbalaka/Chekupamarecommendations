from __future__ import annotations

import re

from chatbot.models import ChatMessage
from learning.models import AssessmentQuestion, Course


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return {token for token in TOKEN_PATTERN.findall((text or "").lower()) if len(token) > 2}


def _overlap_score(left: str, right: str) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = left_tokens & right_tokens
    union = left_tokens | right_tokens
    return len(overlap) / len(union)


def find_similar_existing_questions(query: str, course: Course | None = None, limit: int = 3) -> list[dict]:
    matches: list[dict] = []

    question_queryset = AssessmentQuestion.objects.select_related("assessment__course", "topic")
    if course:
        question_queryset = question_queryset.filter(assessment__course=course)
    for question in question_queryset[:100]:
        score = _overlap_score(query, question.prompt)
        if score <= 0:
            continue
        matches.append(
            {
                "kind": "assessment",
                "text": question.prompt,
                "score": round(score, 2),
                "course": question.assessment.course.code,
                "topic": question.topic.title if question.topic else "",
            }
        )

    message_queryset = ChatMessage.objects.select_related("session__course").filter(sender=ChatMessage.Sender.STUDENT)
    if course:
        message_queryset = message_queryset.filter(session__course=course)
    for previous_message in message_queryset.order_by("-created_at")[:150]:
        score = _overlap_score(query, previous_message.content)
        if score <= 0:
            continue
        matches.append(
            {
                "kind": "chat",
                "text": previous_message.content,
                "score": round(score, 2),
                "course": previous_message.session.course.code if previous_message.session.course else "",
                "topic": "",
            }
        )

    ranked = sorted(matches, key=lambda item: item["score"], reverse=True)
    deduped: list[dict] = []
    seen_texts: set[str] = set()
    for item in ranked:
        key = item["text"].strip().lower()
        if key in seen_texts:
            continue
        seen_texts.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped
