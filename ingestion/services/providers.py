import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib import parse, request
from urllib.error import HTTPError, URLError

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
PROVIDER_REQUEST_TIMEOUT = float(os.getenv("PROVIDER_REQUEST_TIMEOUT_SECONDS", "2.5"))
PROVIDER_DISCOVERY_BUDGET = float(os.getenv("PROVIDER_DISCOVERY_BUDGET_SECONDS", "5"))


def _get_json(url: str, headers=None, timeout_seconds: float = PROVIDER_REQUEST_TIMEOUT):
    req = request.Request(url, headers=headers or {})
    with request.urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _provider_payload(name: str, status: str, results=None, message: str = ""):
    return {"name": name, "status": status, "results": results or [], "message": message}


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
        pdf_url = item.get("content", {}).get("pdf_url", "")
        if pdf_url or item.get("id"):
            pdf_url = pdf_url or f"{OPENALEX_CONTENT_BASE_URL}/works/{item.get('id', '').split('/')[-1]}.pdf"
        results.append(
            {
                "title": item.get("title", ""),
                "year": item.get("publication_year"),
                "source_provider": "OpenAlex",
                "source_endpoint": f"{OPENALEX_BASE_URL}/works",
                "source_type": Material.SourceType.PAPER,
                "original_source_url": item.get("primary_location", {}).get("landing_page_url", ""),
                "source_citation": item.get("doi", ""),
                "source_record_id": item.get("id", ""),
                "authors": ", ".join(author.get("author", {}).get("display_name", "") for author in item.get("authorships", [])),
                "external_url": item.get("primary_location", {}).get("landing_page_url", ""),
                "pdf_url": pdf_url,
                "license": item.get("best_oa_location", {}).get("license", ""),
                "openalex_id": item.get("id", ""),
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
                "source_type": Material.SourceType.PAPER,
                "original_source_url": item.get("URL", ""),
                "external_url": item.get("URL", ""),
                "source_citation": item.get("DOI", ""),
                "source_record_id": item.get("DOI", ""),
                "authors": ", ".join(
                    " ".join(filter(None, [author.get("given"), author.get("family")]))
                    for author in item.get("author", [])
                ),
                "description": item.get("container-title", [""])[0] if item.get("container-title") else "",
            }
        )
    return results


def search_semantic_scholar(query: str, limit: int = 5, timeout_seconds: float = PROVIDER_REQUEST_TIMEOUT):
    headers = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + parse.urlencode(
        {"query": query, "limit": limit, "fields": "title,year,url,authors"}
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
                "source_type": Material.SourceType.PAPER,
                "original_source_url": item.get("url", ""),
                "external_url": item.get("url", ""),
                "source_citation": item.get("paperId", ""),
                "source_record_id": item.get("paperId", ""),
                "authors": ", ".join(author.get("name", "") for author in item.get("authors", [])),
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
                "source_type": Material.SourceType.PAPER,
                "original_source_url": landing_url,
                "external_url": landing_url,
                "source_citation": item.get("doi", item.get("identifier", "")),
                "source_record_id": item.get("identifier", item.get("doi", "")),
                "authors": ", ".join(creator.get("creator", "") for creator in item.get("creators", [])),
                "description": item.get("abstract", "") or item.get("publicationName", ""),
                "pdf_url": pdf_url,
            }
        )
    return results


def discover_external_content(query: str, limit_per_provider: int = 3):
    providers = []
    merged_results = []

    configured_providers = []
    if OPENALEX_API_KEY:
        configured_providers.append(("OpenAlex", lambda: search_openalex(query, per_page=limit_per_provider)))
    else:
        providers.append(_provider_payload("OpenAlex", "missing_key", message="No OPENALEX_API_KEY configured."))

    configured_providers.append(("Crossref", lambda: search_crossref(query, rows=limit_per_provider)))
    configured_providers.append(("Semantic Scholar", lambda: search_semantic_scholar(query, limit=limit_per_provider)))

    if SPRINGER_API_KEY:
        configured_providers.append(("Springer Nature", lambda: search_springer(query, page_size=limit_per_provider)))
    else:
        providers.append(_provider_payload("Springer Nature", "missing_key", message="No SPRINGER_API_KEY configured."))

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
                    else:
                        status = "unavailable"
                    providers.append(_provider_payload(name, status, message=str(exc)))
        except TimeoutError:
            pass

        completed = {future_map[future] for future in future_map if future.done()}
        for name in [provider_name for provider_name, _ in configured_providers]:
            if name not in completed and not any(item["name"] == name for item in providers):
                providers.append(_provider_payload(name, "timed_out", message="Provider search exceeded the fast chat time budget."))

    providers.append(
        _provider_payload(
            "YouTube",
            "manual_only",
            message="YouTube resources are manual-only embeds/uploads in this platform.",
        )
    )

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
            "source_endpoint": item.get("source_endpoint", ""),
            "source_record_id": item.get("source_record_id", ""),
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
            "name": "YouTube",
            "configured": True,
            "mode": "manual_only",
            "endpoint": "manual embed",
            "status": "manual_only",
        }
    )
    return health
