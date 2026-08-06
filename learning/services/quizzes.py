import json
import re
from decimal import Decimal

from django.db import transaction

from ingestion.models import ContentChunk
from learning.models import QuizAnswer, QuizAttempt, QuizQuestion
from recommendations.services.llm import generate_chat_text


QUIZ_JSON_FIELDS = {
    "prompt",
    "question_type",
    "options",
    "correct_answer",
    "explanation",
    "source_material_id",
}


def parse_quiz_json(raw: str) -> list[dict]:
    """Parse only a complete JSON array (optionally inside one JSON code fence)."""

    cleaned = (raw or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, flags=re.I)
    if fenced:
        cleaned = fenced.group(1).strip()
    if not cleaned.startswith("[") or not cleaned.endswith("]"):
        return []
    try:
        payload = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    if not isinstance(payload, list) or not payload:
        return []
    return payload


def validate_quiz_json(payload: list, *, allowed_material_ids: set[int], count: int) -> list[dict]:
    """Reject the whole response unless every requested question matches the schema."""

    if not isinstance(payload, list) or not payload or len(payload) > count:
        return []
    validated = []
    for item in payload:
        if not isinstance(item, dict) or set(item) != QUIZ_JSON_FIELDS:
            return []
        if not isinstance(item["prompt"], str) or not item["prompt"].strip():
            return []
        if item["question_type"] not in QuizQuestion.QuestionType.values:
            return []
        if not isinstance(item["options"], list) or not all(isinstance(option, str) for option in item["options"]):
            return []
        options = [option.strip() for option in item["options"] if option.strip()]
        correct = item["correct_answer"]
        if not isinstance(correct, str) or not correct.strip():
            return []
        correct = correct.strip()
        if not isinstance(item["explanation"], str):
            return []
        if not isinstance(item["source_material_id"], int) or item["source_material_id"] not in allowed_material_ids:
            return []
        if item["question_type"] == QuizQuestion.QuestionType.MULTIPLE_CHOICE:
            if len(options) < 2 or correct not in options:
                return []
        elif options:
            return []
        validated.append({**item, "prompt": item["prompt"].strip(), "options": options, "correct_answer": correct})
    return validated


def _fallback_questions(materials, count: int) -> list[dict]:
    drafts = []
    for material in materials:
        chunk = material.content_chunks.order_by("ordinal").first()
        if not chunk:
            continue
        sentence = next((part.strip() for part in re.split(r"(?<=[.!?])\s+", chunk.text) if len(part.split()) >= 8), chunk.text)
        keywords = [word for word in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", sentence)[:5]]
        drafts.append(
            {
                "prompt": f"Using {material.title}, explain this idea in your own words: {sentence[:220]}",
                "question_type": QuizQuestion.QuestionType.SHORT_TEXT,
                "options": [],
                "correct_answer": ", ".join(keywords),
                "explanation": sentence[:500],
                "source_material_id": material.pk,
            }
        )
        if len(drafts) >= count:
            break
    return drafts


@transaction.atomic
def generate_quiz_questions(quiz, materials, *, count: int, question_type: str = "mixed"):
    materials = list(materials)
    chunks = list(
        ContentChunk.objects.filter(material__in=materials, material__course=quiz.course)
        .select_related("material")
        .order_by("material_id", "ordinal")[:30]
    )
    context = "\n\n".join(
        f"[Material ID {chunk.material_id}: {chunk.material.title}]\n{chunk.text}" for chunk in chunks
    )[:18000]
    system = (
        "Create quiz questions using only the supplied indexed excerpts. Return only a JSON array. "
        "Each object must contain prompt, question_type (mcq or text), options (array), correct_answer, "
        "explanation, and source_material_id. MCQ correct_answer must exactly equal one option. "
        "Short-text correct_answer should be comma-separated marking keywords."
    )
    prompt = f"Create {count} {question_type} questions.\n\nIndexed excerpts:\n{context}"
    allowed_material_ids = {material.pk for material in materials}
    raw, backend = generate_chat_text(system, [prompt]) if context else ("", "fallback")
    valid = validate_quiz_json(parse_quiz_json(raw), allowed_material_ids=allowed_material_ids, count=count)
    if raw and not valid:
        repair_system = (
            "Repair the candidate into one valid JSON array and return JSON only. Do not include prose or markdown. "
            "Do not invent new facts. Every object must contain exactly the required quiz fields: prompt, "
            "question_type, options, correct_answer, explanation, source_material_id. Return [] if repair is impossible."
        )
        repaired_raw, repair_backend = generate_chat_text(repair_system, [raw[:12000]])
        valid = validate_quiz_json(
            parse_quiz_json(repaired_raw), allowed_material_ids=allowed_material_ids, count=count
        )
        if valid:
            backend = f"{repair_backend}-json-repair"
    if not valid:
        valid = _fallback_questions(materials, count)
        backend = "deterministic-fallback"

    starting_order = quiz.questions.count()
    created = []
    for index, item in enumerate(valid[:count], start=1):
        created.append(
            QuizQuestion.objects.create(
                quiz=quiz,
                source_material_id=item.get("source_material_id"),
                prompt=str(item.get("prompt", ""))[:4000],
                question_type=item.get("question_type", QuizQuestion.QuestionType.SHORT_TEXT),
                options=item.get("options", []),
                correct_answer=str(item.get("correct_answer", ""))[:2000],
                explanation=str(item.get("explanation", ""))[:4000],
                points=1,
                order=starting_order + index,
                is_ai_generated=True,
                generation_backend=backend,
            )
        )
    return created, backend


@transaction.atomic
def grade_quiz(quiz, student, cleaned_data):
    questions = list(quiz.questions.all())
    max_score = sum(question.points for question in questions)
    attempt = QuizAttempt.objects.create(quiz=quiz, student=student, max_score=max_score)
    score = Decimal("0")
    for question in questions:
        response = str(cleaned_data.get(f"question_{question.pk}", "")).strip()
        if question.question_type == QuizQuestion.QuestionType.MULTIPLE_CHOICE:
            is_correct = response.casefold() == question.correct_answer.strip().casefold()
        else:
            keywords = [item.strip().casefold() for item in question.correct_answer.split(",") if item.strip()]
            response_lower = response.casefold()
            keyword_matches = sum(keyword in response_lower for keyword in keywords)
            is_correct = bool(keywords) and keyword_matches >= max(1, (len(keywords) + 1) // 2)
        awarded = Decimal(question.points if is_correct else 0)
        QuizAnswer.objects.create(
            attempt=attempt,
            question=question,
            response=response,
            is_correct=is_correct,
            awarded_points=awarded,
        )
        score += awarded
    attempt.score = score
    attempt.save(update_fields=["score"])
    return attempt
