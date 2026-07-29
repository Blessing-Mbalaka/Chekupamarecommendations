from urllib.parse import urlparse


FREE_ACADEMIC_PROVIDERS = [
    "Crossref",
    "OpenAlex",
    "Semantic Scholar",
]


def identify_resource_type(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    return "website"


def provider_summary() -> str:
    return ", ".join(FREE_ACADEMIC_PROVIDERS)
