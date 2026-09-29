from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from urllib import parse, request

from django.db import transaction

from ingestion.models import ResearchRun, ResearchTheme, ResearchVideo, ResearchVideoTheme
from learning.models import Material
from ingestion.services.vector_store import clean_text, index_material
from ingestion.services.providers import (
    SERPAPI_API_KEY,
    fetch_serpapi_youtube_transcript,
    search_serpapi_youtube,
)


YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_API_ROOT = "https://www.googleapis.com/youtube/v3"
STOP_WORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been", "before", "being", "between",
    "but", "can", "could", "does", "for", "from", "have", "how", "into", "just", "more", "most", "not",
    "only", "other", "our", "out", "that", "the", "their", "then", "there", "these", "they", "this", "through",
    "too", "use", "using", "video", "was", "what", "when", "where", "which", "will", "with", "would", "you", "your",
}


class YouTubeResearchError(RuntimeError):
    pass


def extract_video_id(url: str) -> str:
    parsed = parse.urlparse(url.strip())
    host = parsed.netloc.lower().split(":")[0]
    if host in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/").split("/")[0]
    if host.endswith("youtube.com"):
        if parsed.path == "/watch":
            return parse.parse_qs(parsed.query).get("v", [""])[0]
        match = re.match(r"/(?:embed|shorts|live)/([^/?]+)", parsed.path)
        return match.group(1) if match else ""
    return ""


def _get_json(url: str, timeout: float = 12):
    req = request.Request(url, headers={"User-Agent": "RecommendationEngine/1.0"})
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _youtube_api(resource: str, params: dict) -> dict:
    if not YOUTUBE_API_KEY:
        raise YouTubeResearchError("YOUTUBE_API_KEY is not configured.")
    params = {**params, "key": YOUTUBE_API_KEY}
    return _get_json(f"{YOUTUBE_API_ROOT}/{resource}?{parse.urlencode(params)}")


def resolve_seed_title(seed_url: str) -> tuple[str, str]:
    video_id = extract_video_id(seed_url)
    if not video_id:
        raise YouTubeResearchError("Enter a valid YouTube watch, short, live, or youtu.be URL.")
    if YOUTUBE_API_KEY:
        data = _youtube_api("videos", {"part": "snippet", "id": video_id})
        items = data.get("items", [])
        if not items:
            raise YouTubeResearchError("YouTube could not find that video.")
        return video_id, items[0]["snippet"]["title"]
    # oEmbed still allows the seed title to be derived from a public URL; search itself requires the API key.
    data = _get_json("https://www.youtube.com/oembed?" + parse.urlencode({"url": seed_url, "format": "json"}))
    return video_id, data.get("title", "").strip()


def title_to_research_query(title: str) -> str:
    title = re.sub(r"\([^)]*(?:official|video|audio|lyrics)[^)]*\)", " ", title, flags=re.I)
    title = re.sub(r"\[[^]]*(?:official|video|audio|lyrics)[^]]*\]", " ", title, flags=re.I)
    title = re.sub(r"\b(?:official|full|hd|4k|explained|tutorial|lecture)\b", " ", title, flags=re.I)
    return clean_text(title).strip(" -|:")[:500]


def search_videos(query: str, limit: int) -> list[dict]:
    if not YOUTUBE_API_KEY and SERPAPI_API_KEY:
        return search_serpapi_youtube(query, page_size=limit, timeout_seconds=12)
    search = _youtube_api(
        "search",
        {"part": "snippet", "q": query, "type": "video", "maxResults": min(limit, 50), "safeSearch": "moderate"},
    )
    ids = [item.get("id", {}).get("videoId") for item in search.get("items", [])]
    ids = [item for item in ids if item]
    if not ids:
        return []
    details = _youtube_api("videos", {"part": "snippet,contentDetails,statistics", "id": ",".join(ids)})
    by_id = {item["id"]: item for item in details.get("items", [])}
    results = []
    for video_id in ids:
        item = by_id.get(video_id, {})
        snippet = item.get("snippet", {})
        thumbnails = snippet.get("thumbnails", {})
        thumb = thumbnails.get("medium") or thumbnails.get("default") or {}
        results.append(
            {
                "youtube_id": video_id,
                "title": snippet.get("title", "Untitled YouTube video"),
                "description": snippet.get("description", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt", ""),
                "duration": item.get("contentDetails", {}).get("duration", ""),
                "thumbnail_url": thumb.get("url", ""),
                "metadata": {"statistics": item.get("statistics", {}), "raw_tags": snippet.get("tags", [])},
            }
        )
    return results


def _document_terms(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z][a-z0-9'-]{2,}", text.lower()) if word not in STOP_WORDS]


def extract_themes(documents: list[str], count: int, model: str = "lda") -> tuple[list[dict], list[list[float]], str]:
    count = min(count, max(1, len(documents)))
    if model == "bertopic":
        try:
            from bertopic import BERTopic

            topic_model = BERTopic(nr_topics=count, verbose=False)
            labels, probabilities = topic_model.fit_transform(documents)
            topic_ids = [item for item in sorted(set(labels)) if item >= 0][:count]
            themes = []
            for topic_id in topic_ids:
                words = [word for word, _ in topic_model.get_topic(topic_id)[:6]]
                themes.append({"label": " / ".join(words[:3]).title(), "keywords": words})
            weights = []
            for row, label in enumerate(labels):
                weights.append([float(probabilities[row][idx]) if getattr(probabilities, "ndim", 1) > 1 else float(label == topic_id) for idx, topic_id in enumerate(topic_ids)])
            if themes:
                return themes, weights, "bertopic"
        except (ImportError, ValueError, TypeError):
            pass
    try:
        from sklearn.decomposition import LatentDirichletAllocation
        from sklearn.feature_extraction.text import CountVectorizer

        vectorizer = CountVectorizer(stop_words="english", max_features=1500, min_df=1, ngram_range=(1, 2))
        matrix = vectorizer.fit_transform(documents)
        lda = LatentDirichletAllocation(n_components=count, random_state=42, learning_method="batch")
        weights_array = lda.fit_transform(matrix)
        names = vectorizer.get_feature_names_out()
        themes = []
        for component in lda.components_:
            words = [names[index] for index in component.argsort()[-6:][::-1]]
            themes.append({"label": " / ".join(words[:3]).title(), "keywords": words})
        return themes, weights_array.tolist(), "lda"
    except (ImportError, ValueError):
        global_terms = [word for word, _ in Counter(term for doc in documents for term in _document_terms(doc)).most_common(count * 6)]
        buckets = [global_terms[index::count][:6] for index in range(count)]
        themes = [{"label": " / ".join(words[:3]).title() or f"Theme {i + 1}", "keywords": words} for i, words in enumerate(buckets)]
        weights = []
        for doc in documents:
            terms = Counter(_document_terms(doc))
            raw = [sum(terms[word] for word in theme["keywords"]) for theme in themes]
            total = sum(raw) or 1
            weights.append([value / total for value in raw])
        return themes, weights, "keyword-fallback"


@transaction.atomic
def run_youtube_research(*, seed_url, course, topic, video_count, theme_count, topic_model, created_by) -> ResearchRun:
    video_id, seed_title = resolve_seed_title(seed_url)
    query = title_to_research_query(seed_title)
    run = ResearchRun.objects.create(
        course=course, topic=topic, seed_url=seed_url, seed_video_id=video_id, seed_title=seed_title,
        research_query=query, requested_video_count=video_count, topic_model=topic_model, created_by=created_by,
    )
    try:
        results = search_videos(query, video_count)
        if not results:
            raise YouTubeResearchError("YouTube returned no videos for the title-derived research query.")
        videos = []
        documents = []
        for item in results:
            source_text = clean_text(f"{item['title']} {item['description']}")
            material, _ = Material.objects.update_or_create(
                course=course, source_provider="YouTube", source_record_id=item["youtube_id"],
                defaults={
                    "topic": topic, "title": item["title"][:255], "description": item["description"],
                    "source_origin": Material.SourceOrigin.EXTERNAL, "source_type": Material.SourceType.VIDEO,
                    "source_endpoint": "YouTube Data API v3", "external_url": f"https://www.youtube.com/watch?v={item['youtube_id']}",
                    "original_source_url": f"https://www.youtube.com/watch?v={item['youtube_id']}",
                    "youtube_title": item["title"][:255], "uploaded_by": created_by,
                },
            )
            research_video = ResearchVideo.objects.create(
                run=run, material=material, transcript="", transcript_status="awaiting_upload", **item
            )
            videos.append(research_video)
            documents.append(source_text)
        themes, weights, actual_model = extract_themes(documents, theme_count, topic_model)
        run.topic_model = actual_model
        for index, theme_data in enumerate(themes):
            angle = (2 * math.pi * index) / max(1, len(themes))
            theme = ResearchTheme.objects.create(
                run=run, label=theme_data["label"][:160], keywords=theme_data["keywords"],
                description="Theme extracted from titles, descriptions, and available transcripts.",
                x=50 + 28 * math.cos(angle), y=50 + 28 * math.sin(angle), radius=24 + min(18, len(videos) * 2),
            )
            for video_index, video in enumerate(videos):
                weight = weights[video_index][index] if index < len(weights[video_index]) else 0
                if weight >= 0.12 or weight == max(weights[video_index], default=0):
                    ResearchVideoTheme.objects.create(video=video, theme=theme, weight=weight)
        run.status = ResearchRun.Status.PARTIAL
        run.save(update_fields=["status", "topic_model"])
    except Exception as exc:
        run.status = ResearchRun.Status.FAILED
        run.error_message = str(exc)[:2000]
        run.save(update_fields=["status", "error_message"])
        raise
    return run


def _strip_transcript_markup(value: str) -> str:
    value = re.sub(r"^WEBVTT.*?$", " ", value, flags=re.I | re.M)
    value = re.sub(r"^\d+\s*$", " ", value, flags=re.M)
    value = re.sub(r"\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}\s*-->\s*[^\n]+", " ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    return clean_text(value)


@transaction.atomic
def store_uploaded_transcript(video: ResearchVideo, raw_text: str) -> ResearchVideo:
    transcript = _strip_transcript_markup(raw_text)
    if not transcript:
        raise YouTubeResearchError("The uploaded transcript did not contain readable text.")
    video.transcript = transcript
    video.transcript_status = "uploaded"
    video.save(update_fields=["transcript", "transcript_status"])
    video.material.semantic_text = transcript
    video.material.save(update_fields=["semantic_text"])
    index_material(video.material, text=transcript, research_video=video)
    rebuild_run_themes(video.run)
    return video


def store_serpapi_transcript(video: ResearchVideo, language_code: str = "en") -> ResearchVideo:
    try:
        payload = fetch_serpapi_youtube_transcript(video.youtube_id, language_code=language_code)
    except Exception as exc:
        raise YouTubeResearchError(f"SerpApi transcript retrieval failed: {exc}") from exc
    transcript = _strip_transcript_markup(payload.get("text", ""))
    if not transcript:
        raise YouTubeResearchError("SerpApi did not return a readable transcript for this video.")
    stored = store_uploaded_transcript(video, transcript)
    stored.transcript_status = "serpapi"
    stored.metadata = {
        **stored.metadata,
        "transcript_provider": "SerpApi",
        "transcript_language": language_code,
        "transcript_segment_count": len(payload.get("segments", [])),
    }
    stored.save(update_fields=["transcript_status", "metadata"])
    return stored


def store_material_serpapi_transcript(material: Material, language_code: str = "en") -> int:
    video_id = material.youtube_video_id
    if not video_id:
        raise YouTubeResearchError("This material does not contain a valid YouTube video URL.")
    try:
        payload = fetch_serpapi_youtube_transcript(video_id, language_code=language_code)
    except Exception as exc:
        raise YouTubeResearchError(f"SerpApi transcript retrieval failed: {exc}") from exc
    transcript = _strip_transcript_markup(payload.get("text", ""))
    if not transcript:
        raise YouTubeResearchError("SerpApi did not return a readable transcript for this video.")
    material.semantic_text = transcript
    material.source_endpoint = "SerpApi youtube_video_transcript"
    material.save(update_fields=["semantic_text", "source_endpoint"])
    return len(index_material(material, text=transcript))


@transaction.atomic
def rebuild_run_themes(run: ResearchRun) -> None:
    videos = list(run.videos.select_related("material"))
    documents = [video.transcript or clean_text(f"{video.title} {video.description}") for video in videos]
    requested_count = max(2, min(10, run.themes.count() or 5))
    themes, weights, actual_model = extract_themes(documents, requested_count, run.topic_model)
    run.themes.all().delete()
    for index, theme_data in enumerate(themes):
        angle = (2 * math.pi * index) / max(1, len(themes))
        theme = ResearchTheme.objects.create(
            run=run, label=theme_data["label"][:160], keywords=theme_data["keywords"],
            description="Theme extracted from metadata and manually uploaded transcripts.",
            x=50 + 28 * math.cos(angle), y=50 + 28 * math.sin(angle), radius=24 + min(18, len(videos) * 2),
        )
        for video_index, video in enumerate(videos):
            weight = weights[video_index][index] if index < len(weights[video_index]) else 0
            if weight >= 0.12 or weight == max(weights[video_index], default=0):
                ResearchVideoTheme.objects.create(video=video, theme=theme, weight=weight)
    run.topic_model = actual_model
    run.status = ResearchRun.Status.COMPLETE if all(video.transcript for video in videos) else ResearchRun.Status.PARTIAL
    run.save(update_fields=["topic_model", "status"])
