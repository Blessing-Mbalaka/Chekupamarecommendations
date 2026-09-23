import json
import os
import time
from urllib import error, request


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api")
OLLAMA_TEXT_MODEL = os.getenv("OLLAMA_TEXT_MODEL", "tinyllama:latest")
OLLAMA_FAST_TEXT_MODEL = os.getenv("OLLAMA_FAST_TEXT_MODEL", "tinyllama:latest")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")
OLLAMA_TAGS_TIMEOUT = float(os.getenv("OLLAMA_TAGS_TIMEOUT_SECONDS", "1"))
OLLAMA_TEXT_TIMEOUT = float(os.getenv("OLLAMA_TEXT_TIMEOUT_SECONDS", "180"))
OLLAMA_EMBED_TIMEOUT = float(os.getenv("OLLAMA_EMBED_TIMEOUT_SECONDS", "2"))
OLLAMA_MODELS_TTL_SECONDS = float(os.getenv("OLLAMA_MODELS_TTL_SECONDS", "15"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.9"))
OLLAMA_TOP_K = int(os.getenv("OLLAMA_TOP_K", "1"))
OLLAMA_REPEAT_PENALTY = float(os.getenv("OLLAMA_REPEAT_PENALTY", "1.1"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "300"))
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


def _generation_options() -> dict:
    """Use one deterministic-leaning profile for sync and streamed RAG answers."""

    return {
        "temperature": OLLAMA_TEMPERATURE,
        "top_p": OLLAMA_TOP_P,
        "top_k": OLLAMA_TOP_K,
        "repeat_penalty": OLLAMA_REPEAT_PENALTY,
        "num_predict": OLLAMA_NUM_PREDICT,
    }


def generate_text(system_instruction: str, prompt: str, *, model: str | None = None, timeout_seconds: float | None = None) -> str:
    if not is_available():
        return ""
    payload = {
        "model": model or OLLAMA_TEXT_MODEL,
        "system": system_instruction,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "30m",
        "options": _generation_options(),
    }
    try:
        data = _post_json(f"{OLLAMA_BASE_URL}/generate", payload, timeout_seconds or OLLAMA_TEXT_TIMEOUT)
    except (error.URLError, TimeoutError, ValueError):
        return ""
    return data.get("response", "").strip()


def generate_text_stream(
    system_instruction: str,
    prompt: str,
    *,
    model: str | None = None,
    timeout_seconds: float | None = None,
):
    payload = {
        "model": model or OLLAMA_TEXT_MODEL,
        "system": system_instruction,
        "prompt": prompt,
        "stream": True,
        "keep_alive": "30m",
        "options": _generation_options(),
    }
    req = request.Request(
        f"{OLLAMA_BASE_URL}/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds or OLLAMA_TEXT_TIMEOUT) as response:
            for raw_line in response:
                if not raw_line.strip():
                    continue
                data = json.loads(raw_line.decode("utf-8"))
                token = data.get("response", "")
                if token:
                    yield token
                if data.get("done"):
                    break
    except (error.URLError, TimeoutError, ValueError):
        return


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


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    if not texts or not is_available():
        return []
    results: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = [text[:6000] for text in texts[start : start + batch_size]]
        payload = {"model": OLLAMA_EMBED_MODEL, "input": batch}
        try:
            data = _post_json(f"{OLLAMA_BASE_URL}/embed", payload, max(OLLAMA_EMBED_TIMEOUT, 30))
        except (error.URLError, TimeoutError, ValueError):
            return []
        embeddings = data.get("embeddings") or []
        if len(embeddings) != len(batch):
            return []
        results.extend(embeddings)
    return results
