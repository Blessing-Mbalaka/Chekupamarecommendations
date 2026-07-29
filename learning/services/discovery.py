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
    grouped = defaultdict(list)
    for result in payload["results"]:
        grouped[result.get("source_provider", "Unknown")].append(result)
    payload["grouped_results"] = dict(grouped)
    return payload


def import_curated_results(payload: dict, *, course, topic=None, uploaded_by=None):
    return persist_external_results(payload, course=course, topic=topic, uploaded_by=uploaded_by)


def curated_provider_health():
    return [item for item in provider_health() if item["name"] in REPUTABLE_PROVIDER_NAMES or item["name"] == "YouTube"]
