import json
import os
from urllib import error, request


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api")
OLLAMA_TEXT_MODEL = os.getenv("OLLAMA_TEXT_MODEL", "ministral-3:3b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")


def _get_json(url: str):
    with request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict):
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def list_models():
    try:
        data = _get_json(f"{OLLAMA_BASE_URL}/tags")
    except (error.URLError, TimeoutError, ValueError):
        return []
    return data.get("models", [])


def is_available() -> bool:
    return bool(list_models())


def generate_text(system_instruction: str, prompt: str) -> str:
    if not is_available():
        return ""
    payload = {
        "model": OLLAMA_TEXT_MODEL,
        "system": system_instruction,
        "prompt": prompt,
        "stream": False,
    }
    try:
        data = _post_json(f"{OLLAMA_BASE_URL}/generate", payload)
    except (error.URLError, TimeoutError, ValueError):
        return ""
    return data.get("response", "").strip()


def embed_text(text: str):
    if not text.strip() or not is_available():
        return []
    payload = {
        "model": OLLAMA_EMBED_MODEL,
        "input": text[:6000],
    }
    try:
        data = _post_json(f"{OLLAMA_BASE_URL}/embed", payload)
    except (error.URLError, TimeoutError, ValueError):
        return []
    embeddings = data.get("embeddings") or []
    return embeddings[0] if embeddings else []
