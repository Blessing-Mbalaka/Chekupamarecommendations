from decimal import Decimal

from learning.models import AssessmentAttempt, Material
from recommendations.models import Recommendation

from .llm import cosine_similarity, embed_text


def _tokenize(text: str) -> set[str]:
    return {token.strip(" ,.;:!?").lower() for token in text.split() if token.strip(" ,.;:!?")}


def _material_text(material: Material) -> str:
    return " ".join(
        filter(
            None,
            [
                material.title,
                material.description,
                material.tags,
                material.youtube_title,
                material.source_provider,
                material.source_citation,
                material.topic.title if material.topic else "",
                material.course.title,
            ],
        )
    )


def _get_material_embedding(material: Material, *, allow_generation: bool = True):
    if material.embedding:
        return material.embedding, material.source_provider or "cached"
    if not allow_generation:
        return [], "skipped"
    source_text = material.semantic_text or _material_text(material)
    embedding, backend = embed_text(source_text)
    if embedding:
        material.semantic_text = source_text
        material.embedding = embedding
        material.save(update_fields=["semantic_text", "embedding"])
    return embedding, backend


def recommend_for_student(
    student,
    course=None,
    query_text="",
    limit=5,
    *,
    use_semantic=True,
    generate_missing_embeddings=True,
):
    materials = Material.objects.select_related("course", "topic").filter(is_validated=True)
    if course is not None:
        materials = materials.filter(course=course)
    material_list = list(materials)
    if not material_list:
        return []

    profile = getattr(student, "student_profile", None)
    profile_text = " ".join(
        filter(
            None,
            [
                getattr(profile, "challenges", ""),
                getattr(profile, "goals", ""),
                getattr(profile, "identifiers", ""),
                query_text,
            ],
        )
    )
    interest_tokens = _tokenize(profile_text)
    query_embedding, _ = embed_text(profile_text) if profile_text and use_semantic else ([], "fallback")

    weak_topics = []
    attempts = (
        AssessmentAttempt.objects.filter(student=student)
        .select_related("assessment__course")
        .prefetch_related("answers__question__topic")
        .order_by("-submitted_at")[:5]
    )
    for attempt in attempts:
        for answer in attempt.answers.all():
            if not answer.is_correct and answer.question.topic:
                weak_topics.append(answer.question.topic.title.lower())
    weak_tokens = _tokenize(" ".join(weak_topics))

    scored = []
    for material in material_list:
        score = Decimal("0")
        haystack = _material_text(material).lower()

        for token in interest_tokens:
            if token and token in haystack:
                score += Decimal("3")
        for token in weak_tokens:
            if token and token in haystack:
                score += Decimal("5")
        if material.publication_year:
            score += Decimal("1")
        if material.source_type in {Material.SourceType.PAPER, Material.SourceType.VIDEO}:
            score += Decimal("1.5")
        if material.source_origin == Material.SourceOrigin.EXTERNAL:
            score += Decimal("0.5")

        material_embedding, _ = (
            _get_material_embedding(material, allow_generation=generate_missing_embeddings)
            if query_embedding
            else ([], "fallback")
        )
        semantic_score = cosine_similarity(query_embedding, material_embedding) if query_embedding and material_embedding else 0.0
        if semantic_score > 0:
            score += Decimal(str(round(semantic_score * 10, 2)))

        if score > 0:
            scored.append((score, material))

    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return material_list[:limit]
    return [material for _, material in scored[:limit]]


def store_recommendations(student, materials, related_message=None):
    recommendations = []
    for index, material in enumerate(materials, start=1):
        recommendation = Recommendation.objects.create(
            student=student,
            material=material,
            reason="Matched against profile challenges, baseline weak areas, and recent chatbot question.",
            score=Decimal(max(1, len(materials) - index + 1)),
            related_message_id=getattr(related_message, "id", None),
        )
        recommendations.append(recommendation)
    return recommendations
