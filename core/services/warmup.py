from django.core.cache import cache

from ingestion.services.providers import discover_external_content
from recommendations.services.llm import refine_search_query


SYSTEMS_THINKING_WARMUP_QUESTIONS = [
    "How do feedback loops affect system stability in a supply chain?",
    "What are the best beginner resources for systems thinking and causal loop diagrams?",
    "How do delays and unintended consequences change policy outcomes in a complex system?",
]


def warmup_systems_thinking_cache() -> list[dict]:
    warmed_entries = []
    for index, question in enumerate(SYSTEMS_THINKING_WARMUP_QUESTIONS, start=1):
        refined_query, backend = refine_search_query(question, lecturer_text="systems thinking")
        discovery = discover_external_content(refined_query, limit_per_provider=1)
        cache_key = f"warmup_systems_thinking_{index}"
        payload = {
            "question": question,
            "refined_query": refined_query,
            "backend": backend,
            "provider_statuses": discovery["providers"],
        }
        cache.set(cache_key, payload, timeout=60 * 60 * 12)
        warmed_entries.append(payload)
    cache.set("warmup_systems_thinking_keys", [f"warmup_systems_thinking_{i}" for i in range(1, len(warmed_entries) + 1)], timeout=60 * 60 * 12)
    return warmed_entries
