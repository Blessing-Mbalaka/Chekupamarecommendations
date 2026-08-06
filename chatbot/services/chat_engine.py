import re
from hashlib import sha256
from urllib.parse import urlparse

from django.core.cache import cache

from chatbot.models import ChatMessage
from ingestion.services.vector_store import retrieve_chunks
from learning.models import Course, Material
from learning.services.discovery import REPUTABLE_PROVIDER_NAMES, discover_curated_content, import_curated_results
from recommendations.services.engine import store_recommendations
from recommendations.services.llm import backend_status, generate_chat_text
from analytics_app.services.questions import classify_systems_question, record_relevant_question


def _safe_link(value: str, *, allow_relative: bool = False) -> str:
    value = (value or "").strip()
    if allow_relative and value.startswith("/") and not value.startswith("//"):
        return value
    return value if urlparse(value).scheme in {"http", "https"} else ""


def _material_payload(material: Material, *, number=None, score=0, role="source") -> dict:
    return {
        "number": number,
        "material_id": material.pk,
        "title": material.title,
        "score": score,
        "url": material.get_absolute_url(),
        "external_url": _safe_link(material.effective_source_url),
        "preview_kind": material.preview_kind,
        "preview_url": _safe_link(material.preview_url, allow_relative=True),
        "provider": material.source_provider,
        "source_type": material.get_source_type_display(),
        "authors": material.authors,
        "publication": " · ".join(
            filter(None, [material.journal_name, str(material.publication_year or ""), material.publisher])
        ),
        "doi": material.doi,
        "topics": material.discovered_topics,
        "origin": material.source_origin,
        "origin_label": (
            "Additional material"
            if material.source_origin == Material.SourceOrigin.EXTERNAL
            else "Prescribed material"
        ),
        "role": role,
    }


def _refresh_academic_discovery(query: str, *, course=None) -> dict:
    """Refresh reputable API suggestions without admitting metadata into RAG."""

    cache_key = "chat-academic-discovery:" + sha256(query.strip().lower().encode("utf-8")).hexdigest()
    payload = cache.get(cache_key)
    if payload is None:
        try:
            payload = discover_curated_content(
                query,
                selected_providers=REPUTABLE_PROVIDER_NAMES,
                limit_per_provider=5,
            )
        except Exception as exc:
            return {
                "statuses": [{"name": "Academic discovery", "status": "unavailable", "message": str(exc), "count": 0}],
                "material_ids": [],
            }
        cache.set(cache_key, payload, timeout=15 * 60)
    materials = []
    if course and payload.get("results"):
        try:
            materials = import_curated_results(payload, course=course)
        except Exception as exc:
            payload = {
                **payload,
                "providers": [
                    *payload.get("providers", []),
                    {
                        "name": "Academic discovery import",
                        "status": "unavailable",
                        "message": str(exc),
                        "results": [],
                    },
                ],
            }
    return {
        "statuses": [
            {
                "name": item.get("name", "Unknown provider"),
                "status": item.get("status", "unknown"),
                "message": item.get("message", ""),
                "count": len(item.get("results", [])),
            }
            for item in payload.get("providers", [])
        ],
        "material_ids": [material.pk for material in materials],
    }


def _external_suggestions(query: str, *, course=None, exclude_ids=None, include_ids=None, limit=2) -> list[dict]:
    queryset = Material.objects.filter(
        is_validated=True,
        source_origin=Material.SourceOrigin.EXTERNAL,
    ).select_related("course", "topic")
    if course:
        queryset = queryset.filter(course=course)
    if exclude_ids:
        queryset = queryset.exclude(pk__in=exclude_ids)
    if include_ids is not None:
        queryset = queryset.filter(pk__in=include_ids)
    query_tokens = {token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 2}
    ranked = []
    for material in queryset[:100]:
        haystack = " ".join(
            filter(
                None,
                [
                    material.title,
                    material.description,
                    material.authors,
                    material.journal_name,
                    material.publisher,
                    material.doi,
                    material.tags,
                    material.youtube_title,
                ],
            )
        ).lower()
        overlap = sum(1 for token in query_tokens if token in haystack)
        ranked.append((overlap, material.created_at, material))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [
        _material_payload(material, number=index, role="suggestion")
        for index, (_, _, material) in enumerate(ranked[:limit], start=1)
    ]


def _is_video_query(query: str) -> bool:
    return bool(re.search(r"\b(video|videos|youtube|yt|clip|clips|watch)\b", query.lower()))


def _dedupe_matches_by_material(ranked_matches: list[dict]) -> list[dict]:
    deduped = []
    seen_material_ids = set()
    for match in ranked_matches:
        material_id = match["material"].pk
        if material_id in seen_material_ids:
            continue
        deduped.append(match)
        seen_material_ids.add(material_id)
    return deduped


def _select_matches(query: str, ranked_matches: list[dict]) -> list[dict]:
    deduped_matches = _dedupe_matches_by_material(ranked_matches)
    if _is_video_query(query):
        video_matches = [
            item for item in deduped_matches if item["material"].source_type == Material.SourceType.VIDEO
        ]
        return video_matches[:1]

    matches = deduped_matches[:5]
    for origin in (Material.SourceOrigin.EXTERNAL, Material.SourceOrigin.INTERNAL):
        if any(item["material"].source_origin == origin for item in matches):
            continue
        candidate = next((item for item in deduped_matches if item["material"].source_origin == origin), None)
        if candidate:
            matches = (matches[:4] + [candidate]) if len(matches) >= 5 else (matches + [candidate])
    return matches


def _analytics_filter_payload(reason: str) -> dict:
    return {
        "text": (
            "That message is unrelated to systems thinking or the indexed course material, so it was "
            "automatically filtered out of question analytics. Please ask a systems-thinking course question."
        ),
        "metadata": {
            "rag_only": True,
            "grounded": False,
            "response_backend": "relevance-filter",
            "analytics_filtered": True,
            "classification_reason": reason,
            "sources": [],
            "external_suggestions": [],
            "provider_statuses": [],
            "ollama_status": backend_status(include_models=False),
        },
    }


def _infer_course(course, ranked_matches: list[dict]):
    return course or (ranked_matches[0]["material"].course if ranked_matches else None) or Course.objects.filter(
        title__icontains="system"
    ).first()


def _build_grounded_response(
    query: str,
    *,
    ranked_matches: list[dict],
    inferred_course=None,
    student=None,
    related_message: ChatMessage | None = None,
):
    discovery = _refresh_academic_discovery(query, course=inferred_course)
    provider_statuses = discovery["statuses"]
    discovered_material_ids = discovery["material_ids"]
    matches = _select_matches(query, ranked_matches)

    if not matches:
        return {
            "text": (
                "I can’t answer that from the indexed course library yet. "
                "Ask a lecturer to upload a source document or a transcript for a researched YouTube video."
            ),
            "metadata": {
                "rag_only": True,
                "grounded": False,
                "response_backend": "rag-empty",
                "sources": [],
                "external_suggestions": _external_suggestions(
                    query,
                    course=inferred_course,
                    include_ids=discovered_material_ids or None,
                    limit=max(2, len(discovered_material_ids)),
                ),
                "provider_statuses": provider_statuses,
                "ollama_status": backend_status(include_models=False),
            },
        }

    materials = []
    seen_material_ids = set()
    context_blocks = []
    sources = []
    for index, match in enumerate(matches, start=1):
        material = match["material"]
        context_blocks.append(f"[Source {index}: {material.title}]\n{match['text']}")
        sources.append(_material_payload(material, number=index, score=match["score"]))
        if material.pk not in seen_material_ids:
            materials.append(material)
            seen_material_ids.add(material.pk)

    system_instruction = (
        "You are a retrieval-only course assistant. Answer using only the supplied source excerpts. "
        "Do not add outside facts. Cite factual claims inline as [Source N]. If the excerpts do not answer "
        "the question, say the indexed library does not contain the answer."
    )
    contents = [f"Question: {query}", "Indexed excerpts:\n\n" + "\n\n".join(context_blocks)]
    answer_signature = "|".join(
        [query.strip().lower(), *[str(match["chunk"].pk) for match in matches]]
    )
    answer_cache_key = "chat-rag-answer:" + sha256(answer_signature.encode("utf-8")).hexdigest()
    cached_answer = cache.get(answer_cache_key)
    if cached_answer:
        generated_text, backend = cached_answer["text"], f"{cached_answer['backend']}-cache"
    else:
        generated_text, backend = generate_chat_text(system_instruction, contents)
        if generated_text:
            cache.set(answer_cache_key, {"text": generated_text, "backend": backend}, timeout=5 * 60)
    if not generated_text:
        excerpt = matches[0]["text"][:700].strip()
        generated_text = f"The closest indexed source says: {excerpt} [Source 1]"
        backend = "extractive-rag"

    if student:
        store_recommendations(student, materials[:3], related_message=related_message)
    suggestion_limit = 1 if _is_video_query(query) else len(discovered_material_ids)
    external_suggestions = _external_suggestions(
        query,
        course=inferred_course,
        exclude_ids=seen_material_ids,
        include_ids=discovered_material_ids,
        limit=suggestion_limit,
    )
    if not external_suggestions and not any(
        material.source_origin == Material.SourceOrigin.EXTERNAL for material in materials
    ):
        external_suggestions = _external_suggestions(
            query,
            course=inferred_course,
            exclude_ids=seen_material_ids,
        )
    return {
        "text": generated_text,
        "metadata": {
            "rag_only": True,
            "grounded": True,
            "response_backend": backend,
            "sources": sources,
            "external_suggestions": external_suggestions,
            "provider_statuses": provider_statuses,
            "ollama_status": backend_status(include_models=False),
        },
    }


def generate_grounded_response_for_query(
    query: str,
    *,
    course=None,
    student=None,
    related_message: ChatMessage | None = None,
    track_analytics: bool = False,
):
    """Run the retrieval-only answer flow for a plain-text query."""

    ranked_matches = retrieve_chunks(query, course=course, limit=12)
    inferred_course = _infer_course(course, ranked_matches)
    classification = classify_systems_question(
        query,
        course=inferred_course,
        ranked_matches=ranked_matches,
    )
    if not classification["relevant"]:
        return _analytics_filter_payload(classification["reason"])

    if track_analytics and related_message:
        record_relevant_question(related_message, classification, course=inferred_course)

    return _build_grounded_response(
        query,
        ranked_matches=ranked_matches,
        inferred_course=inferred_course,
        student=student,
        related_message=related_message,
    )


def generate_bot_response(message: ChatMessage):
    """Answer only from persisted chunks while separately suggesting labelled external material."""

    return generate_grounded_response_for_query(
        message.content,
        course=message.session.course,
        student=message.session.student,
        related_message=message,
        track_analytics=True,
    )
