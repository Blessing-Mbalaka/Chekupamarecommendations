import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib import parse, request
from urllib.error import HTTPError, URLError

import serpapi

from learning.models import Material


OPENALEX_BASE_URL = os.getenv("OPENALEX_BASE_URL", "https://api.openalex.org")
OPENALEX_CONTENT_BASE_URL = os.getenv("OPENALEX_CONTENT_BASE_URL", "https://content.openalex.org")
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "")
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "")
CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "")
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
SPRINGER_API_BASE_URL = os.getenv("SPRINGER_API_BASE_URL", "https://api.springernature.com")
SPRINGER_API_KEY = os.getenv("SPRINGER_API_KEY", "")
SPRINGER_META_ENDPOINT = os.getenv("SPRINGER_META_ENDPOINT", "/meta/v2/json")
SPRINGER_OPENACCESS_ENDPOINT = os.getenv("SPRINGER_OPENACCESS_ENDPOINT", "/openaccess/json")
SPRINGER_METADATA_ENDPOINT = os.getenv("SPRINGER_METADATA_ENDPOINT", "/metadata/json")
SPRINGER_FULLTEXT_ENDPOINT = os.getenv("SPRINGER_FULLTEXT_ENDPOINT", "/xmldata/jats")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "") or os.getenv("SERPAPI_KEY", "")
SERPAPI_BASE_URL = os.getenv("SERPAPI_BASE_URL", "https://serpapi.com/search")
SERPAPI_SCHOLAR_RESULTS = max(1, min(20, int(os.getenv("SERPAPI_SCHOLAR_RESULTS", "10"))))
PROVIDER_REQUEST_TIMEOUT = float(os.getenv("PROVIDER_REQUEST_TIMEOUT_SECONDS", "2.5"))
PROVIDER_DISCOVERY_BUDGET = float(os.getenv("PROVIDER_DISCOVERY_BUDGET_SECONDS", "5"))


def _get_json(url: str, headers=None, timeout_seconds: float = PROVIDER_REQUEST_TIMEOUT):
    req = request.Request(url, headers=headers or {})
    with request.urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _provider_payload(name: str, status: str, results=None, message: str = ""):
    return {"name": name, "status": status, "results": results or [], "message": message}


def _safe_dict(value):
    return value if isinstance(value, dict) else {}


def _openalex_work_id(record_id: str) -> str:
    return (record_id or "").rstrip("/").split("/")[-1]


def _normalize_springer_urls(record: dict):
    urls = record.get("url", []) or []
    if isinstance(urls, list):
        landing = next((item.get("value", "") for item in urls if item.get("format") in {"html", "web"}), "")
        pdf = next((item.get("value", "") for item in urls if item.get("format") == "pdf"), "")
    else:
        landing = ""
        pdf = ""
    return landing, pdf


def search_openalex(query: str, per_page: int = 5, timeout_seconds: float = PROVIDER_REQUEST_TIMEOUT):
    params = {"search": query, "per-page": per_page, "api_key": OPENALEX_API_KEY}
    if OPENALEX_EMAIL:
        params["mailto"] = OPENALEX_EMAIL
    url = f"{OPENALEX_BASE_URL}/works?" + parse.urlencode(params)
    data = _get_json(url, timeout_seconds=timeout_seconds)
    results = []
    for item in data.get("results", []):
        content = _safe_dict(item.get("content"))
        primary_location = _safe_dict(item.get("primary_location"))
        best_oa_location = _safe_dict(item.get("best_oa_location"))
        primary_source = _safe_dict(primary_location.get("source"))
        work_id = _openalex_work_id(item.get("id", ""))
        pdf_url = content.get("pdf_url", "")
        if pdf_url or work_id:
            pdf_url = pdf_url or f"/learning/materials/openalex/{work_id}/pdf/"
        results.append(
            {
                "title": item.get("title", ""),
                "year": item.get("publication_year"),
                "source_provider": "OpenAlex",
                "source_endpoint": f"{OPENALEX_BASE_URL}/works",
                "source_type": Material.SourceType.JOURNAL,
                "original_source_url": primary_location.get("landing_page_url", ""),
                "source_citation": item.get("doi", ""),
                "source_record_id": item.get("id", ""),
                "authors": ", ".join(author.get("author", {}).get("display_name", "") for author in item.get("authorships", [])),
                "doi": (item.get("doi", "") or "").removeprefix("https://doi.org/"),
                "journal_name": primary_source.get("display_name", ""),
                "publisher": primary_source.get("host_organization_name", ""),
                "external_url": primary_location.get("landing_page_url", ""),
                "pdf_url": pdf_url,
                "license": best_oa_location.get("license", ""),
                "openalex_id": item.get("id", ""),
                "openalex_work_id": work_id,
                "description": item.get("abstract_inverted_index", {}) and "Abstract available via OpenAlex metadata." or "",
            }
        )
    return results


def search_crossref(query: str, rows: int = 5, timeout_seconds: float = PROVIDER_REQUEST_TIMEOUT):
    params = {"query": query, "rows": rows}
    if CROSSREF_MAILTO:
        params["mailto"] = CROSSREF_MAILTO
    url = "https://api.crossref.org/works?" + parse.urlencode(params)
    data = _get_json(url, timeout_seconds=timeout_seconds)
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
                "source_endpoint": "https://api.crossref.org/works",
                "source_type": Material.SourceType.JOURNAL,
                "original_source_url": item.get("URL", ""),
                "external_url": item.get("URL", ""),
                "source_citation": item.get("DOI", ""),
                "source_record_id": item.get("DOI", ""),
                "authors": ", ".join(
                    " ".join(filter(None, [author.get("given"), author.get("family")]))
                    for author in item.get("author", [])
                ),
                "doi": item.get("DOI", ""),
                "publisher": item.get("publisher", ""),
                "journal_name": item.get("container-title", [""])[0] if item.get("container-title") else "",
                "volume_issue": " / ".join(filter(None, [item.get("volume", ""), item.get("issue", "")])),
                "isbn": ", ".join(item.get("ISBN", []) or []),
                "description": item.get("container-title", [""])[0] if item.get("container-title") else "",
            }
        )
    return results


def search_semantic_scholar(query: str, limit: int = 5, timeout_seconds: float = PROVIDER_REQUEST_TIMEOUT):
    headers = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + parse.urlencode(
        {"query": query, "limit": limit, "fields": "title,year,url,authors,journal,externalIds,openAccessPdf"}
    )
    data = _get_json(url, headers=headers, timeout_seconds=timeout_seconds)
    results = []
    for item in data.get("data", []):
        results.append(
            {
                "title": item.get("title", ""),
                "year": item.get("year"),
                "source_provider": "Semantic Scholar",
                "source_endpoint": "https://api.semanticscholar.org/graph/v1/paper/search",
                "source_type": Material.SourceType.JOURNAL,
                "original_source_url": item.get("url", ""),
                "external_url": item.get("url", ""),
                "source_citation": item.get("paperId", ""),
                "source_record_id": item.get("paperId", ""),
                "authors": ", ".join(author.get("name", "") for author in item.get("authors", [])),
                "doi": _safe_dict(item.get("externalIds")).get("DOI", ""),
                "journal_name": _safe_dict(item.get("journal")).get("name", ""),
                "volume_issue": _safe_dict(item.get("journal")).get("volume", ""),
                "pdf_url": _safe_dict(item.get("openAccessPdf")).get("url", ""),
                "description": "Semantic Scholar result",
            }
        )
    return results


def search_springer(query: str, endpoint_path: str | None = None, page_size: int = 5, timeout_seconds: float = PROVIDER_REQUEST_TIMEOUT):
    endpoint_path = endpoint_path or SPRINGER_META_ENDPOINT
    params = {
        "api_key": SPRINGER_API_KEY,
        "q": f'keyword:"{query}"',
        "s": 1,
        "p": page_size,
    }
    url = f"{SPRINGER_API_BASE_URL}{endpoint_path}?" + parse.urlencode(params)
    data = _get_json(url, timeout_seconds=timeout_seconds)
    results = []
    for item in data.get("records", []):
        landing_url, pdf_url = _normalize_springer_urls(item)
        publication_date = item.get("publicationDate", "")
        results.append(
            {
                "title": item.get("title", ""),
                "year": publication_date[:4] if publication_date else None,
                "source_provider": "Springer Nature",
                "source_endpoint": f"{SPRINGER_API_BASE_URL}{endpoint_path}",
                "source_type": Material.SourceType.JOURNAL,
                "original_source_url": landing_url,
                "external_url": landing_url,
                "source_citation": item.get("doi", item.get("identifier", "")),
                "source_record_id": item.get("identifier", item.get("doi", "")),
                "authors": ", ".join(creator.get("creator", "") for creator in item.get("creators", [])),
                "doi": item.get("doi", ""),
                "publisher": item.get("publisher", "Springer Nature"),
                "journal_name": item.get("publicationName", ""),
                "volume_issue": " / ".join(filter(None, [item.get("volume", ""), item.get("number", "")])),
                "description": item.get("abstract", "") or item.get("publicationName", ""),
                "pdf_url": pdf_url,
            }
        )
    return results


def search_serpapi_scholar(query: str, page_size: int = 5, timeout_seconds: float = PROVIDER_REQUEST_TIMEOUT):
    client = serpapi.Client(api_key=SERPAPI_API_KEY, timeout=timeout_seconds)
    data = client.search(
        {
            "engine": "google_scholar",
            "q": query,
            "hl": "en",
            "num": page_size,
        }
    )
    results = []
    for item in data.get("organic_results", []):
        publication_info = item.get("publication_info", {}).get("summary", "")
        links = item.get("resources", []) or []
        pdf_url = next((resource.get("link", "") for resource in links if resource.get("file_format") == "PDF"), "")
        results.append(
            {
                "title": item.get("title", ""),
                "year": item.get("year"),
                "source_provider": "Google Scholar (SerpApi)",
                "source_endpoint": SERPAPI_BASE_URL,
                "source_type": Material.SourceType.JOURNAL,
                "original_source_url": item.get("link", ""),
                "external_url": item.get("link", ""),
                "source_citation": publication_info,
                "source_record_id": item.get("result_id", ""),
                "authors": publication_info,
                "description": item.get("snippet", ""),
                "pdf_url": pdf_url,
            }
        )
    return results


def search_serpapi_youtube(query: str, page_size: int = 10, timeout_seconds: float = PROVIDER_REQUEST_TIMEOUT):
    if not SERPAPI_API_KEY:
        raise RuntimeError("SERPAPI_API_KEY is not configured.")
    client = serpapi.Client(api_key=SERPAPI_API_KEY, timeout=timeout_seconds)
    data = client.search({"engine": "youtube", "search_query": query, "hl": "en"})
    results = []
    for item in list(data.get("video_results", []))[:page_size]:
        video_id = item.get("video_id", "")
        if not video_id and item.get("link"):
            video_id = parse.parse_qs(parse.urlparse(item["link"]).query).get("v", [""])[0]
        if not video_id:
            continue
        thumbnail = item.get("thumbnail", {})
        if isinstance(thumbnail, dict):
            thumbnail = thumbnail.get("static") or thumbnail.get("rich") or ""
        channel = item.get("channel", {})
        results.append(
            {
                "youtube_id": video_id,
                "title": item.get("title", "Untitled YouTube video"),
                "description": item.get("description", ""),
                "channel_title": channel.get("name", "") if isinstance(channel, dict) else str(channel or ""),
                "published_at": item.get("published_date", ""),
                "duration": item.get("length", ""),
                "thumbnail_url": thumbnail,
                "metadata": {"views": item.get("views"), "serpapi_link": item.get("serpapi_link", "")},
            }
        )
    return results


def fetch_serpapi_youtube_transcript(
    video_id: str,
    language_code: str = "en",
    timeout_seconds: float = 12,
) -> dict:
    if not SERPAPI_API_KEY:
        raise RuntimeError("SERPAPI_API_KEY is not configured.")
    client = serpapi.Client(api_key=SERPAPI_API_KEY, timeout=timeout_seconds)
    data = client.search(
        {
            "engine": "youtube_video_transcript",
            "v": video_id,
            "language_code": language_code,
        }
    )
    snippets = data.get("transcript", []) or []
    text = " ".join(item.get("snippet", "").strip() for item in snippets if item.get("snippet"))
    return {
        "text": text,
        "segments": snippets,
        "available_transcripts": data.get("available_transcripts", []) or [],
    }


def discover_external_content(query: str, limit_per_provider: int = 3, selected_providers=None):
    providers = []
    merged_results = []
    selected = set(
        selected_providers
        or ["OpenAlex", "Crossref", "Semantic Scholar", "Springer Nature", "Google Scholar (SerpApi)", "YouTube"]
    )

    configured_providers = []
    if "OpenAlex" in selected and OPENALEX_API_KEY:
        configured_providers.append(("OpenAlex", lambda: search_openalex(query, per_page=limit_per_provider)))
    elif "OpenAlex" in selected:
        providers.append(_provider_payload("OpenAlex", "missing_key", message="No OPENALEX_API_KEY configured."))

    if "Crossref" in selected:
        configured_providers.append(("Crossref", lambda: search_crossref(query, rows=limit_per_provider)))
    if "Semantic Scholar" in selected:
        configured_providers.append(("Semantic Scholar", lambda: search_semantic_scholar(query, limit=limit_per_provider)))

    if "Springer Nature" in selected and SPRINGER_API_KEY:
        configured_providers.append(("Springer Nature", lambda: search_springer(query, page_size=limit_per_provider)))
    elif "Springer Nature" in selected:
        providers.append(_provider_payload("Springer Nature", "missing_key", message="No SPRINGER_API_KEY configured."))
    if "Google Scholar (SerpApi)" in selected and SERPAPI_API_KEY:
        configured_providers.append(
            (
                "Google Scholar (SerpApi)",
                lambda: search_serpapi_scholar(
                    query,
                    page_size=max(limit_per_provider, SERPAPI_SCHOLAR_RESULTS),
                ),
            )
        )
    elif "Google Scholar (SerpApi)" in selected:
        providers.append(_provider_payload("Google Scholar (SerpApi)", "missing_key", message="No SERPAPI_API_KEY configured."))

    future_map = {}
    with ThreadPoolExecutor(max_workers=max(1, len(configured_providers))) as executor:
        for name, func in configured_providers:
            future_map[executor.submit(func)] = name

        try:
            for future in as_completed(future_map, timeout=PROVIDER_DISCOVERY_BUDGET):
                name = future_map[future]
                try:
                    results = future.result()
                    providers.append(_provider_payload(name, "ok", results))
                    merged_results.extend(results)
                except (HTTPError, URLError, TimeoutError, ValueError) as exc:
                    if name == "OpenAlex":
                        status = "quota_exhausted" if getattr(exc, "code", None) in {402, 429} else "unavailable"
                    elif name == "Semantic Scholar":
                        status = "quota_exhausted" if getattr(exc, "code", None) == 429 else "unavailable"
                    elif name == "Springer Nature":
                        status = "quota_exhausted" if getattr(exc, "code", None) in {401, 403, 429} else "unavailable"
                    elif name == "Google Scholar (SerpApi)":
                        status = "quota_exhausted" if getattr(exc, "code", None) in {401, 403, 429} else "unavailable"
                    else:
                        status = "unavailable"
                    providers.append(_provider_payload(name, status, message=str(exc)))
                except Exception as exc:
                    providers.append(_provider_payload(name, "unavailable", message=f"{type(exc).__name__}: {exc}"))
        except TimeoutError:
            pass

        completed = {future_map[future] for future in future_map if future.done()}
        for name in [provider_name for provider_name, _ in configured_providers]:
            if name not in completed and not any(item["name"] == name for item in providers):
                providers.append(_provider_payload(name, "timed_out", message="Provider search exceeded the fast chat time budget."))

    if "YouTube" in selected:
        providers.append(
            _provider_payload(
                "YouTube",
                "configured" if SERPAPI_API_KEY else "manual_only",
                message=(
                    "SerpApi YouTube discovery and transcript fallback is configured."
                    if SERPAPI_API_KEY
                    else "YouTube transcripts require manual upload until SerpApi is configured."
                ),
            )
        )

    return {"query": query, "providers": providers, "results": merged_results}


def persist_external_results(discovery_payload: dict, course=None, topic=None, uploaded_by=None):
    materials = []
    for item in discovery_payload.get("results", []):
        title = (item.get("title") or "").strip()
        url = item.get("external_url") or item.get("original_source_url") or ""
        if not title:
            continue
        defaults = {
            "course": course,
            "topic": topic,
            "description": item.get("description") or "",
            "publication_year": int(item.get("year")) if str(item.get("year", "")).isdigit() else None,
            "authors": item.get("authors") or "",
            "publisher": item.get("publisher") or "",
            "journal_name": item.get("journal_name") or "",
            "volume_issue": item.get("volume_issue") or "",
            "doi": item.get("doi") or "",
            "isbn": item.get("isbn") or "",
            "source_origin": Material.SourceOrigin.EXTERNAL,
            "source_type": item.get("source_type") or Material.SourceType.PAPER,
            "source_provider": item.get("source_provider") or "",
            "source_endpoint": item.get("source_endpoint") or "",
            "source_record_id": item.get("source_record_id") or "",
            "external_url": url,
            "original_source_url": item.get("original_source_url") or url,
            "source_preview_url": item.get("pdf_url") or "",
            "youtube_title": item.get("youtube_title") or "",
            "source_citation": item.get("source_citation") or "",
            "tags": item.get("license") or "",
            "uploaded_by": uploaded_by,
        }
        identity = {"course": course, "title": title}
        if defaults["source_provider"] and defaults["source_record_id"]:
            identity = {
                "course": course,
                "source_provider": defaults["source_provider"],
                "source_record_id": defaults["source_record_id"],
            }
            defaults["title"] = title
        material, _ = Material.objects.update_or_create(defaults=defaults, **identity)
        materials.append(material)
    return materials


def provider_health():
    health = []
    health.append(
        {
            "name": "OpenAlex",
            "configured": bool(OPENALEX_API_KEY),
            "mode": "api",
            "endpoint": f"{OPENALEX_BASE_URL}/works",
            "status": "configured" if OPENALEX_API_KEY else "missing_key",
        }
    )
    health.append(
        {
            "name": "Crossref",
            "configured": True,
            "mode": "api",
            "endpoint": "https://api.crossref.org/works",
            "status": "configured",
        }
    )
    health.append(
        {
            "name": "Semantic Scholar",
            "configured": True,
            "mode": "api",
            "endpoint": "https://api.semanticscholar.org/graph/v1/paper/search",
            "status": "configured_optional_key" if SEMANTIC_SCHOLAR_API_KEY else "public_mode",
        }
    )
    health.append(
        {
            "name": "Springer Nature",
            "configured": bool(SPRINGER_API_KEY),
            "mode": "api",
            "endpoint": f"{SPRINGER_API_BASE_URL}{SPRINGER_META_ENDPOINT}",
            "status": "configured" if SPRINGER_API_KEY else "missing_key",
        }
    )
    health.append(
        {
            "name": "Google Scholar (SerpApi)",
            "configured": bool(SERPAPI_API_KEY),
            "mode": "api",
            "endpoint": f"{SERPAPI_BASE_URL}?engine=google_scholar",
            "status": "configured" if SERPAPI_API_KEY else "missing_key",
        }
    )
    health.append(
        {
            "name": "YouTube",
            "configured": bool(SERPAPI_API_KEY),
            "mode": "api_fallback" if SERPAPI_API_KEY else "manual_only",
            "endpoint": "SerpApi youtube / youtube_video_transcript" if SERPAPI_API_KEY else "manual embed",
            "status": "configured" if SERPAPI_API_KEY else "manual_only",
        }
    )
    return health
