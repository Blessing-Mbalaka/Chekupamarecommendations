import json
import os
from urllib import parse, request
from urllib.error import HTTPError, URLError

from learning.models import Material


OPENALEX_BASE_URL = os.getenv("OPENALEX_BASE_URL", "https://api.openalex.org")
OPENALEX_CONTENT_BASE_URL = os.getenv("OPENALEX_CONTENT_BASE_URL", "https://content.openalex.org")
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "")
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "")
CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "")
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")


def _get_json(url: str, headers=None):
    req = request.Request(url, headers=headers or {})
    with request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _provider_payload(name: str, status: str, results=None, message: str = ""):
    return {"name": name, "status": status, "results": results or [], "message": message}


def search_openalex(query: str, per_page: int = 5):
    params = {"search": query, "per-page": per_page, "api_key": OPENALEX_API_KEY}
    if OPENALEX_EMAIL:
        params["mailto"] = OPENALEX_EMAIL
    url = f"{OPENALEX_BASE_URL}/works?" + parse.urlencode(params)
    data = _get_json(url)
    results = []
    for item in data.get("results", []):
        pdf_url = item.get("content", {}).get("pdf_url", "")
        if pdf_url or item.get("id"):
            pdf_url = pdf_url or f"{OPENALEX_CONTENT_BASE_URL}/works/{item.get('id', '').split('/')[-1]}.pdf"
        results.append(
            {
                "title": item.get("title", ""),
                "year": item.get("publication_year"),
                "source_provider": "OpenAlex",
                "source_type": Material.SourceType.PAPER,
                "original_source_url": item.get("primary_location", {}).get("landing_page_url", ""),
                "source_citation": item.get("doi", ""),
                "authors": ", ".join(author.get("author", {}).get("display_name", "") for author in item.get("authorships", [])),
                "external_url": item.get("primary_location", {}).get("landing_page_url", ""),
                "pdf_url": pdf_url,
                "license": item.get("best_oa_location", {}).get("license", ""),
                "openalex_id": item.get("id", ""),
                "description": item.get("abstract_inverted_index", {}) and "Abstract available via OpenAlex metadata." or "",
            }
        )
    return results


def search_crossref(query: str, rows: int = 5):
    params = {"query": query, "rows": rows}
    if CROSSREF_MAILTO:
        params["mailto"] = CROSSREF_MAILTO
    url = "https://api.crossref.org/works?" + parse.urlencode(params)
    data = _get_json(url)
    results = []
    for item in data.get("message", {}).get("items", []):
        title = item.get("title", [""])
        published = item.get("published-print", item.get("published-online", {})).get("date-parts", [[None]])
        year = published[0][0] if published and published[0] else None
        results.append(
            {
                "title": title[0] if title else "",
                "year": year,
                "source_provider": "Crossref",
                "source_type": Material.SourceType.PAPER,
                "original_source_url": item.get("URL", ""),
                "external_url": item.get("URL", ""),
                "source_citation": item.get("DOI", ""),
                "authors": ", ".join(
                    " ".join(filter(None, [author.get("given"), author.get("family")]))
                    for author in item.get("author", [])
                ),
                "description": item.get("container-title", [""])[0] if item.get("container-title") else "",
            }
        )
    return results


def search_semantic_scholar(query: str, limit: int = 5):
    headers = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + parse.urlencode(
        {"query": query, "limit": limit, "fields": "title,year,url,authors"}
    )
    data = _get_json(url, headers=headers)
    results = []
    for item in data.get("data", []):
        results.append(
            {
                "title": item.get("title", ""),
                "year": item.get("year"),
                "source_provider": "Semantic Scholar",
                "source_type": Material.SourceType.PAPER,
                "original_source_url": item.get("url", ""),
                "external_url": item.get("url", ""),
                "source_citation": item.get("paperId", ""),
                "authors": ", ".join(author.get("name", "") for author in item.get("authors", [])),
                "description": "Semantic Scholar result",
            }
        )
    return results


def search_youtube(query: str, max_results: int = 5):
    if not YOUTUBE_API_KEY:
        return []
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY,
    }
    url = "https://www.googleapis.com/youtube/v3/search?" + parse.urlencode(params)
    data = _get_json(url)
    results = []
    for item in data.get("items", []):
        video_id = item.get("id", {}).get("videoId", "")
        snippet = item.get("snippet", {})
        results.append(
            {
                "title": snippet.get("title", ""),
                "year": (snippet.get("publishedAt", "") or "")[:4] or None,
                "source_provider": "YouTube",
                "source_type": Material.SourceType.VIDEO,
                "original_source_url": f"https://www.youtube.com/watch?v={video_id}",
                "external_url": f"https://www.youtube.com/watch?v={video_id}",
                "source_citation": video_id,
                "authors": snippet.get("channelTitle", ""),
                "description": snippet.get("description", ""),
                "youtube_title": snippet.get("title", ""),
            }
        )
    return results


def discover_external_content(query: str, limit_per_provider: int = 3):
    providers = []
    merged_results = []

    if OPENALEX_API_KEY:
        try:
            openalex_results = search_openalex(query, per_page=limit_per_provider)
            providers.append(_provider_payload("OpenAlex", "ok", openalex_results))
            merged_results.extend(openalex_results)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            status = "quota_exhausted" if getattr(exc, "code", None) in {402, 429} else "unavailable"
            providers.append(_provider_payload("OpenAlex", status, message=str(exc)))
    else:
        providers.append(_provider_payload("OpenAlex", "missing_key", message="No OPENALEX_API_KEY configured."))

    try:
        crossref_results = search_crossref(query, rows=limit_per_provider)
        providers.append(_provider_payload("Crossref", "ok", crossref_results))
        merged_results.extend(crossref_results)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        providers.append(_provider_payload("Crossref", "unavailable", message=str(exc)))

    try:
        semantic_results = search_semantic_scholar(query, limit=limit_per_provider)
        providers.append(_provider_payload("Semantic Scholar", "ok", semantic_results))
        merged_results.extend(semantic_results)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        status = "quota_exhausted" if getattr(exc, "code", None) == 429 else "unavailable"
        providers.append(_provider_payload("Semantic Scholar", status, message=str(exc)))

    if YOUTUBE_API_KEY:
        try:
            youtube_results = search_youtube(query, max_results=limit_per_provider)
            providers.append(_provider_payload("YouTube", "ok", youtube_results))
            merged_results.extend(youtube_results)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            status = "quota_exhausted" if getattr(exc, "code", None) == 403 else "unavailable"
            providers.append(_provider_payload("YouTube", status, message=str(exc)))
    else:
        providers.append(_provider_payload("YouTube", "missing_key", message="No YOUTUBE_API_KEY configured."))

    return {"query": query, "providers": providers, "results": merged_results}


def persist_external_results(discovery_payload: dict, course=None, topic=None, uploaded_by=None):
    materials = []
    for item in discovery_payload.get("results", []):
        title = item.get("title", "").strip()
        url = item.get("external_url") or item.get("original_source_url") or ""
        if not title:
            continue
        defaults = {
            "course": course,
            "topic": topic,
            "description": item.get("description", ""),
            "publication_year": int(item.get("year")) if str(item.get("year", "")).isdigit() else None,
            "source_origin": Material.SourceOrigin.EXTERNAL,
            "source_type": item.get("source_type", Material.SourceType.PAPER),
            "source_provider": item.get("source_provider", ""),
            "external_url": url,
            "original_source_url": item.get("original_source_url", url),
            "youtube_title": item.get("youtube_title", ""),
            "source_citation": item.get("source_citation", ""),
            "tags": item.get("license", ""),
            "uploaded_by": uploaded_by,
            "is_validated": True,
        }
        material, _ = Material.objects.update_or_create(
            course=course,
            title=title,
            defaults=defaults,
        )
        materials.append(material)
    return materials
