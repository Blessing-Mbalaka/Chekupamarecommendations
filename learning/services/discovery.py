from collections import defaultdict

from ingestion.services.providers import (
    discover_external_content,
    persist_external_results,
    provider_health,
)


REPUTABLE_PROVIDER_NAMES = [
    "OpenAlex",
    "Crossref",
    "Semantic Scholar",
    "Springer Nature",
    "Google Scholar (SerpApi)",
]


def discover_curated_content(query: str, *, selected_providers=None, limit_per_provider: int = 3):
    payload = discover_external_content(
        query,
        limit_per_provider=limit_per_provider,
        selected_providers=selected_providers or REPUTABLE_PROVIDER_NAMES,
    )
    indexed_results = []
    grouped = defaultdict(list)
    for index, result in enumerate(payload["results"], start=1):
        enriched = dict(result)
        provider = enriched.get("source_provider", "Unknown")
        record_id = enriched.get("source_record_id") or enriched.get("source_citation") or enriched.get("title", "")
        enriched["import_key"] = f"{provider}:{record_id}:{index}"
        enriched["has_pdf"] = bool(enriched.get("pdf_url"))
        indexed_results.append(enriched)
        grouped[provider].append(enriched)
    payload["results"] = indexed_results
    payload["grouped_results"] = dict(grouped)
    return payload


def import_curated_results(payload: dict, *, course, topic=None, uploaded_by=None):
    return persist_external_results(payload, course=course, topic=topic, uploaded_by=uploaded_by)


def import_curated_selection(payload: dict, import_keys: list[str], *, course, topic=None, uploaded_by=None):
    selected = [item for item in payload.get("results", []) if item.get("import_key") in import_keys]
    return persist_external_results({"results": selected}, course=course, topic=topic, uploaded_by=uploaded_by)


def curated_provider_health():
    return [item for item in provider_health() if item["name"] in REPUTABLE_PROVIDER_NAMES or item["name"] == "YouTube"]
