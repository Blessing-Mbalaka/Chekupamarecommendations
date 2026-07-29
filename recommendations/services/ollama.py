import json
import os
import time
from urllib import error, request


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api")
OLLAMA_TEXT_MODEL = os.getenv("OLLAMA_TEXT_MODEL", "ministral-3:3b")
OLLAMA_FAST_TEXT_MODEL = os.getenv("OLLAMA_FAST_TEXT_MODEL", "tinyllama:latest")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")
OLLAMA_TAGS_TIMEOUT = float(os.getenv("OLLAMA_TAGS_TIMEOUT_SECONDS", "1"))
OLLAMA_TEXT_TIMEOUT = float(os.getenv("OLLAMA_TEXT_TIMEOUT_SECONDS", "2"))
OLLAMA_EMBED_TIMEOUT = float(os.getenv("OLLAMA_EMBED_TIMEOUT_SECONDS", "2"))
OLLAMA_MODELS_TTL_SECONDS = float(os.getenv("OLLAMA_MODELS_TTL_SECONDS", "15"))
MODEL_CACHE = {"models": [], "fetched_at": 0.0}


def _get_json(url: str, timeout_seconds: float):
    with request.urlopen(url, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict, timeout_seconds: float):
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def list_models():
    now = time.time()
    if MODEL_CACHE["models"] and (now - MODEL_CACHE["fetched_at"]) < OLLAMA_MODELS_TTL_SECONDS:
        return MODEL_CACHE["models"]
    try:
        data = _get_json(f"{OLLAMA_BASE_URL}/tags", OLLAMA_TAGS_TIMEOUT)
    except (error.URLError, TimeoutError, ValueError):
        return []
    MODEL_CACHE["models"] = data.get("models", [])
    MODEL_CACHE["fetched_at"] = now
    return MODEL_CACHE["models"]


def is_available() -> bool:
    return bool(list_models())


def generate_text(system_instruction: str, prompt: str, *, model: str | None = None, timeout_seconds: float | None = None) -> str:
    if not is_available():
        return ""
    payload = {
        "model": model or OLLAMA_TEXT_MODEL,
        "system": system_instruction,
        "prompt": prompt,
        "stream": False,
    }
    try:
        data = _post_json(f"{OLLAMA_BASE_URL}/generate", payload, timeout_seconds or OLLAMA_TEXT_TIMEOUT)
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
        data = _post_json(f"{OLLAMA_BASE_URL}/embed", payload, OLLAMA_EMBED_TIMEOUT)
    except (error.URLError, TimeoutError, ValueError):
        return []
    embeddings = data.get("embeddings") or []
    return embeddings[0] if embeddings else []
