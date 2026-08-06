from __future__ import annotations

import json
import re
from collections import Counter

from django.db import transaction
from django.db.models import Q

from chatbot.models import ChatMessage
from ingestion.services.youtube_research import extract_themes
from ingestion.services.vector_store import retrieve_chunks
from learning.models import Course
from recommendations.services.llm import generate_chat_text

from analytics_app.models import AnalyzedQuestion, QuestionTheme


SYSTEMS_TERMS = {
    "system", "systems", "systems thinking", "feedback", "feedback loop", "causal loop",
    "stock", "flow", "leverage point", "boundary", "stakeholder", "emergence", "archetype",
    "complexity", "interdependence", "unintended consequence", "reinforcing", "balancing",
    "mental model", "causal", "dynamic", "holistic", "systemic", "systems map",
}
NOISE_RE = re.compile(
    r"^\s*(?:hi+|hello|hey|yo|thanks?|thank you|ok(?:ay)?|test|help|good\s+(?:morning|afternoon|evening))[.!?\s]*$",
    re.I,
)
OFF_TOPIC_TERMS = {
    "weather", "football", "soccer", "recipe", "celebrity", "rickroll", "lottery", "horoscope",
}
THEME_STOPWORDS = {
    "about", "all", "article", "articles", "can", "could", "define", "describe", "does", "explain",
    "file", "files", "find", "for", "get", "give", "have", "help", "how", "lecture", "lecturer",
    "make", "material", "materials", "need", "note", "notes", "paper", "papers", "pdf", "pdfs",
    "please", "provide", "question", "questions", "show", "student", "students", "suggest", "tell",
    "topic", "topics", "upload", "uploaded", "using", "video", "videos", "watch", "what", "with",
    "would", "youtube", "your", "you", "system", "systems", "thinking", "course",
}


def _normalize_term(term: str) -> str:
    if term.endswith("ies") and len(term) > 4:
        return term[:-3] + "y"
    if term.endswith("s") and not term.endswith("ss") and len(term) > 4:
        return term[:-1]
    return term


def _theme_terms(text: str) -> list[str]:
    tokens = []
    for term in re.findall(r"[a-z][a-z0-9'-]{2,}", (text or "").lower()):
        normalized = _normalize_term(term)
        if normalized in THEME_STOPWORDS:
            continue
        tokens.append(normalized)
    return tokens


def _model_document(text: str) -> str:
    cleaned = " ".join((text or "").split())
    cleaned = re.sub(r"\bsystems?\s+thinking\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(
        r"\b(?:please|could you|can you|find me|tell me|explain|what is|how do|make me|show me|provide|give me|get me)\b",
        " ",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\b(?:video|videos|youtube|material|materials|pdf|file|files|paper|papers)\b", " ", cleaned, flags=re.I)
    cleaned = " ".join(cleaned.split())
    return cleaned or text


def _course_topic_label(course: Course, documents: list[str]) -> str:
    topic_scores = []
    cluster_terms = Counter()
    lowered_documents = [document.lower() for document in documents]
    for document in documents:
        cluster_terms.update(_theme_terms(document))
    for topic in course.topics.all():
        topic_terms = _theme_terms(topic.title)
        if not topic_terms:
            continue
        overlap = sum(cluster_terms[term] for term in topic_terms)
        phrase_bonus = sum(1 for document in lowered_documents if topic.title.lower() in document)
        score = overlap + (phrase_bonus * 3)
        if score > 0:
            topic_scores.append((score, topic.title))
    topic_scores.sort(key=lambda item: (-item[0], item[1]))
    return topic_scores[0][1] if topic_scores else ""


def _cluster_keywords(documents: list[str], *, limit: int = 6) -> list[str]:
    term_counts = Counter()
    phrase_counts = Counter()
    for document in documents:
        terms = _theme_terms(document)
        if not terms:
            continue
        term_counts.update(terms)
        phrase_counts.update(
            " ".join(pair)
            for pair in zip(terms, terms[1:])
            if pair[0] != pair[1]
        )
    ranked = []
    for phrase, weight in phrase_counts.items():
        ranked.append((weight * 2, phrase))
    for term, weight in term_counts.items():
        ranked.append((weight, term))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    keywords = []
    for _, candidate in ranked:
        if candidate in keywords:
            continue
        keywords.append(candidate)
        if len(keywords) == limit:
            break
    return keywords


def _cluster_label(course: Course, documents: list[str], fallback_index: int) -> tuple[str, list[str]]:
    topic_label = _course_topic_label(course, documents)
    keywords = _cluster_keywords(documents)
    if topic_label:
        if topic_label.lower() not in {keyword.lower() for keyword in keywords}:
            keywords = [topic_label.lower(), *keywords][:6]
        return topic_label, keywords
    if keywords:
        return keywords[0].replace("-", " ").title(), keywords
    return f"Theme {fallback_index + 1}", []


def _kmeans_themes(documents: list[str], count: int) -> tuple[list[dict], list[list[float]], str]:
    try:
        from sklearn.cluster import KMeans
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(stop_words="english", max_features=1500, min_df=1, ngram_range=(1, 2))
        matrix = vectorizer.fit_transform(documents)
        cluster_count = min(count, max(1, matrix.shape[0]))
        model = KMeans(n_clusters=cluster_count, random_state=42, n_init=10)
        labels = model.fit_predict(matrix)
        names = vectorizer.get_feature_names_out()
        themes = []
        for center in model.cluster_centers_:
            words = [names[index] for index in center.argsort()[-6:][::-1]]
            themes.append({"label": " / ".join(words[:3]).title(), "keywords": words})
        weights = [[1.0 if labels[row] == idx else 0.0 for idx in range(cluster_count)] for row in range(len(documents))]
        return themes, weights, "kmeans"
    except (ImportError, ValueError):
        return extract_themes(documents, count, "lda")


def _refine_themes(course: Course, documents: list[str], weights: list[list[float]]) -> tuple[list[dict], list[list[float]]]:
    if not weights:
        return [], []
    cluster_count = max((len(row) for row in weights), default=0)
    clustered_documents = [[] for _ in range(cluster_count)]
    for row_index, row_weights in enumerate(weights):
        if not row_weights:
            continue
        cluster_index = max(range(len(row_weights)), key=lambda idx: row_weights[idx])
        clustered_documents[cluster_index].append(documents[row_index])

    raw_themes = []
    original_to_refined = {}
    for cluster_index, cluster_docs in enumerate(clustered_documents):
        if not cluster_docs:
            continue
        label, keywords = _cluster_label(course, cluster_docs, cluster_index)
        raw_themes.append({"label": label[:160], "keywords": keywords})
        original_to_refined[cluster_index] = len(raw_themes) - 1

    merged_themes = []
    refined_map = {}
    final_column_map = {}
    for raw_index, theme in enumerate(raw_themes):
        label = theme["label"]
        if label in refined_map:
            final_index = refined_map[label]
            merged_themes[final_index]["keywords"] = list(
                dict.fromkeys([*merged_themes[final_index]["keywords"], *theme["keywords"]])
            )[:6]
        else:
            final_index = len(merged_themes)
            refined_map[label] = final_index
            merged_themes.append(theme)
        final_column_map[raw_index] = final_index

    refined_weights = []
    for row_weights in weights:
        merged_row = [0.0] * len(merged_themes)
        for original_index, weight in enumerate(row_weights):
            if original_index not in original_to_refined:
                continue
            raw_index = original_to_refined[original_index]
            merged_row[final_column_map[raw_index]] += float(weight)
        refined_weights.append(merged_row)
    return merged_themes, refined_weights


def _build_theme_report(documents: list[str], requested_count: int, requested_model: str, backend: str, themes: list[dict]) -> dict:
    report = {
        "requested_model": requested_model,
        "backend": backend,
        "requested_count": requested_count,
        "document_count": len(documents),
        "theme_labels": [theme["label"] for theme in themes],
        "keywords": [{"label": theme["label"], "keywords": theme.get("keywords", [])[:4]} for theme in themes],
    }
    upper_bound = min(8, max(2, len(documents)))
    if requested_model == "lda":
        try:
            from sklearn.decomposition import LatentDirichletAllocation
            from sklearn.feature_extraction.text import CountVectorizer

            vectorizer = CountVectorizer(stop_words="english", max_features=1500, min_df=1, ngram_range=(1, 2))
            matrix = vectorizer.fit_transform(documents)
            report["metric_label"] = "Perplexity by K (lower is tighter)"
            report["k_curve"] = []
            for cluster_count in range(2, upper_bound + 1):
                lda = LatentDirichletAllocation(n_components=cluster_count, random_state=42, learning_method="batch")
                lda.fit(matrix)
                report["k_curve"].append({"k": cluster_count, "score": round(float(lda.perplexity(matrix)), 2)})
        except (ImportError, ValueError):
            pass
    elif requested_model == "kmeans":
        try:
            from sklearn.cluster import KMeans
            from sklearn.feature_extraction.text import TfidfVectorizer

            vectorizer = TfidfVectorizer(stop_words="english", max_features=1500, min_df=1, ngram_range=(1, 2))
            matrix = vectorizer.fit_transform(documents)
            report["metric_label"] = "Inertia by K (lower is tighter)"
            report["k_curve"] = []
            for cluster_count in range(2, upper_bound + 1):
                model = KMeans(n_clusters=cluster_count, random_state=42, n_init=10)
                model.fit(matrix)
                report["k_curve"].append({"k": cluster_count, "score": round(float(model.inertia_), 2)})
        except (ImportError, ValueError):
            pass
    return report


def _json_object(value: str) -> dict:
    value = (value or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", value, re.I | re.S)
    candidate = fenced.group(1) if fenced else value
    start, end = candidate.find("{"), candidate.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(candidate[start : end + 1])
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def classify_systems_question(text: str, *, course=None, ranked_matches=None, use_llm=True) -> dict:
    """Classify a message without persisting rejected text."""

    cleaned = " ".join((text or "").split()).strip()
    lowered = cleaned.lower()
    tokens = set(re.findall(r"[a-z][a-z0-9'-]{2,}", lowered))
    matched_terms = sorted(term for term in SYSTEMS_TERMS if term in lowered)
    if not cleaned or NOISE_RE.match(cleaned) or len(tokens) < 2:
        return {"relevant": False, "score": 0.0, "backend": "rules", "reason": "Greeting or non-academic noise."}
    if OFF_TOPIC_TERMS & tokens and not matched_terms:
        return {"relevant": False, "score": 0.0, "backend": "rules", "reason": "Unrelated to systems thinking."}
    if matched_terms:
        return {
            "relevant": True,
            "score": min(1.0, 0.82 + (0.03 * len(matched_terms))),
            "backend": "rules",
            "reason": f"Systems-thinking concepts detected: {', '.join(matched_terms[:4])}.",
        }

    course_text = " ".join(filter(None, [getattr(course, "title", ""), getattr(course, "description", "")])).lower()
    academic_cue = re.search(r"\b(?:explain|define|compare|analyse|analyze|evaluate|calculate|describe)\b", lowered)
    if course and "system" not in course_text and academic_cue:
        return {
            "relevant": True,
            "score": 0.72,
            "backend": "course-rules",
            "reason": "Substantive question for the selected non-systems course.",
        }

    ranked_matches = ranked_matches or []
    best_score = float(ranked_matches[0].get("score", 0)) if ranked_matches else 0.0
    if best_score >= 0.45:
        return {
            "relevant": True,
            "score": min(0.9, best_score),
            "backend": "indexed-library",
            "reason": "Strong match to indexed systems-thinking course material.",
        }
    if not use_llm:
        return {"relevant": False, "score": best_score, "backend": "rules", "reason": "No systems-thinking signal."}

    course_context = f"Course: {course.code} - {course.title}. {course.description}" if course else "Course domain: systems thinking."
    instruction = (
        "You are a strict relevance filter for systems-thinking question analytics. "
        "Decide whether the student's message asks a substantive question about systems thinking or the supplied course. "
        "Greetings, requests unrelated to the course, entertainment, and random conversation are unrelated and must be filtered. "
        "Return exactly one JSON object and no prose: "
        '{"relevant":true,"score":0.0,"reason":"short reason"}'
    )
    generated, backend = generate_chat_text(instruction, [course_context, f"Student message: {cleaned}"])
    payload = _json_object(generated)
    relevant = payload.get("relevant") is True
    try:
        score = max(0.0, min(1.0, float(payload.get("score", 0))))
    except (TypeError, ValueError):
        score = 0.0
    if not payload:
        return {"relevant": False, "score": best_score, "backend": f"{backend}-invalid", "reason": "Classifier returned no valid JSON."}
    return {
        "relevant": relevant,
        "score": score,
        "backend": backend,
        "reason": str(payload.get("reason", "Model classification."))[:255],
    }


def record_relevant_question(message: ChatMessage, classification: dict, *, course=None):
    if not classification.get("relevant") or message.sender != ChatMessage.Sender.STUDENT:
        return None
    course = course or message.session.course
    if not course:
        return None
    question, _ = AnalyzedQuestion.objects.get_or_create(
        message=message,
        defaults={
            "course": course,
            "text": message.content,
            "relevance_score": classification.get("score", 1.0),
            "relevance_backend": classification.get("backend", "rules")[:40],
            "classification_reason": classification.get("reason", "")[:255],
        },
    )
    return question


def suggest_question_themes(course: Course, *, count=5, model="lda", created_by=None):
    questions = list(AnalyzedQuestion.objects.filter(course=course).order_by("created_at"))
    if not questions:
        return [], "none", {}
    model_documents = []
    label_documents = []
    for item in questions:
        label_documents.append(item.text)
        model_documents.append(_model_document(item.text))
    if model == "kmeans":
        _, weights, backend = _kmeans_themes(model_documents, count)
    else:
        _, weights, backend = extract_themes(model_documents, count, model)
    themes, weights = _refine_themes(course, label_documents, weights)
    report = _build_theme_report(model_documents, count, model, backend, themes)
    stored = []
    with transaction.atomic():
        stale_theme_ids = list(
            QuestionTheme.objects.filter(course=course, is_model_suggested=True).values_list("pk", flat=True)
        )
        if stale_theme_ids:
            AnalyzedQuestion.objects.filter(course=course, theme_id__in=stale_theme_ids).update(theme=None)
            QuestionTheme.objects.filter(pk__in=stale_theme_ids).delete()
        for theme_data in themes:
            theme, _ = QuestionTheme.objects.get_or_create(
                course=course,
                label=theme_data["label"][:160],
                defaults={
                    "description": "Suggested from student questions. Keywords: " + ", ".join(theme_data.get("keywords", [])),
                    "is_model_suggested": True,
                    "model_backend": backend,
                    "created_by": created_by,
                },
            )
            stored.append(theme)
        for row, question in enumerate(questions):
            row_weights = weights[row] if row < len(weights) else []
            if not stored or not row_weights:
                question.suggested_theme_label = ""
                if question.theme_id in stale_theme_ids:
                    question.theme = None
                    question.save(update_fields=["theme", "suggested_theme_label"])
                else:
                    question.save(update_fields=["suggested_theme_label"])
                continue
            index = max(range(min(len(stored), len(row_weights))), key=lambda idx: row_weights[idx])
            question.suggested_theme_label = stored[index].label
            update_fields = ["suggested_theme_label"]
            if question.theme_id is None or question.theme_id in stale_theme_ids:
                question.theme = stored[index]
                update_fields.append("theme")
            question.save(update_fields=update_fields)
    return stored, backend, report


def backfill_relevant_questions(courses):
    course_ids = list(courses.values_list("pk", flat=True))
    default_systems_course = courses.filter(title__icontains="system").first()
    messages = ChatMessage.objects.filter(
        sender=ChatMessage.Sender.STUDENT,
    ).filter(
        Q(session__course_id__in=course_ids) | Q(session__course__isnull=True)
    ).filter(question_analysis__isnull=True).select_related("session__course")
    created = 0
    for message in messages.iterator():
        course = message.session.course
        if not course:
            ranked = retrieve_chunks(message.content, limit=1)
            candidate = ranked[0]["material"].course if ranked else None
            course = candidate if candidate and candidate.pk in course_ids else default_systems_course
        classification = classify_systems_question(message.content, course=course, use_llm=False)
        if record_relevant_question(message, classification, course=course):
            created += 1
    return created
