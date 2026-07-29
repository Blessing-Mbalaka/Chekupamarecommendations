import json
from urllib import parse, request


def _get_json(url: str):
    with request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def search_openalex(query: str, per_page: int = 5):
    url = "https://api.openalex.org/works?" + parse.urlencode({"search": query, "per-page": per_page})
    data = _get_json(url)
    results = []
    for item in data.get("results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "year": item.get("publication_year"),
                "source_provider": "OpenAlex",
                "original_source_url": item.get("primary_location", {}).get("landing_page_url", ""),
                "source_citation": item.get("doi", ""),
                "authors": ", ".join(author.get("author", {}).get("display_name", "") for author in item.get("authorships", [])),
            }
        )
    return results


def search_crossref(query: str, rows: int = 5):
    url = "https://api.crossref.org/works?" + parse.urlencode({"query": query, "rows": rows})
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
                "original_source_url": item.get("URL", ""),
                "source_citation": item.get("DOI", ""),
                "authors": ", ".join(
                    " ".join(filter(None, [author.get("given"), author.get("family")]))
                    for author in item.get("author", [])
                ),
            }
        )
    return results


def search_semantic_scholar(query: str, limit: int = 5):
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + parse.urlencode(
        {"query": query, "limit": limit, "fields": "title,year,url,authors"}
    )
    data = _get_json(url)
    results = []
    for item in data.get("data", []):
        results.append(
            {
                "title": item.get("title", ""),
                "year": item.get("year"),
                "source_provider": "Semantic Scholar",
                "original_source_url": item.get("url", ""),
                "source_citation": item.get("paperId", ""),
                "authors": ", ".join(author.get("name", "") for author in item.get("authors", [])),
            }
        )
    return results
