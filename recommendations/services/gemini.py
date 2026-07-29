import json
import math
import os
import time
from urllib import error, parse, request


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.6-flash")
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-2")
GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_TEXT_TIMEOUT = float(os.getenv("GEMINI_TEXT_TIMEOUT_SECONDS", "3"))
GEMINI_EMBED_TIMEOUT = float(os.getenv("GEMINI_EMBED_TIMEOUT_SECONDS", "2"))
GEMINI_FAILURE_COOLDOWN = float(os.getenv("GEMINI_FAILURE_COOLDOWN_SECONDS", "60"))
LAST_GEMINI_FAILURE_AT = 0.0


def _cooldown_active() -> bool:
    return LAST_GEMINI_FAILURE_AT and (time.time() - LAST_GEMINI_FAILURE_AT) < GEMINI_FAILURE_COOLDOWN


def _mark_failure() -> None:
    global LAST_GEMINI_FAILURE_AT
    LAST_GEMINI_FAILURE_AT = time.time()


def _mark_success() -> None:
    global LAST_GEMINI_FAILURE_AT
    LAST_GEMINI_FAILURE_AT = 0.0


def _post_json(url: str, payload: dict, timeout_seconds: float):
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def is_configured() -> bool:
    return bool(GEMINI_API_KEY) and not _cooldown_active()


def generate_text(system_instruction: str, contents: list[str]) -> str:
    if not is_configured():
        return ""
    url = f"{GEMINI_API_ROOT}/{GEMINI_TEXT_MODEL}:generateContent?key={parse.quote(GEMINI_API_KEY)}"
    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"parts": [{"text": content}]} for content in contents],
    }
    try:
        data = _post_json(url, payload, GEMINI_TEXT_TIMEOUT)
    except (error.URLError, TimeoutError, ValueError):
        _mark_failure()
        return ""
    _mark_success()

    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    return " ".join(part.get("text", "") for part in parts).strip()


def embed_text(text: str):
    if not is_configured() or not text.strip():
        return []
    url = f"{GEMINI_API_ROOT}/{GEMINI_EMBED_MODEL}:embedContent?key={parse.quote(GEMINI_API_KEY)}"
    payload = {
        "model": f"models/{GEMINI_EMBED_MODEL}",
        "content": {"parts": [{"text": text[:6000]}]},
    }
    try:
        data = _post_json(url, payload, GEMINI_EMBED_TIMEOUT)
    except (error.URLError, TimeoutError, ValueError):
        _mark_failure()
        return []
    _mark_success()

    return data.get("embedding", {}).get("values", [])


def cosine_similarity(left, right) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)
