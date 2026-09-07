import math

from . import gemini, ollama


def cosine_similarity(left, right) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def backend_status(include_models: bool = True):
    models = ollama.list_models() if include_models else []
    return {
        "gemini": gemini.is_configured(),
        "ollama": bool(models) if include_models else ollama.is_available(),
        "ollama_models": [model.get("name", "") for model in models],
    }


def refine_search_query(student_message: str, challenge_text: str = "", lecturer_text: str = "") -> tuple[str, str]:
    system_instruction = (
        "Turn the student message into a short academic search string. "
        "Keep important subject terms, difficulty points, and resource hints. Return only the search string."
    )
    prompt = " | ".join(
        part for part in [student_message.strip(), challenge_text.strip(), lecturer_text.strip()] if part
    )
    if gemini.is_configured():
        refined = gemini.generate_text(system_instruction, [prompt])
        if refined:
            return refined.strip(), "gemini"
    if ollama.is_available():
        refined = ollama.generate_text(
            system_instruction,
            prompt,
            model=ollama.OLLAMA_FAST_TEXT_MODEL,
            timeout_seconds=min(ollama.OLLAMA_TEXT_TIMEOUT, 2),
        )
        if refined:
            return refined.strip(), "ollama"
    return student_message.strip(), "fallback"


def generate_chat_text(system_instruction: str, contents: list[str]) -> tuple[str, str]:
    if gemini.is_configured():
        response = gemini.generate_text(system_instruction, contents)
        if response:
            return response, "gemini"
    if ollama.is_available():
        response = ollama.generate_text(
            system_instruction,
            "\n".join(contents),
            model=ollama.OLLAMA_TEXT_MODEL,
            timeout_seconds=ollama.OLLAMA_TEXT_TIMEOUT,
        )
        if response:
            return response, "ollama"
    return "", "fallback"


def generate_chat_text_stream(system_instruction: str, contents: list[str]):
    if ollama.is_available():
        return (
            ollama.generate_text_stream(
                system_instruction,
                "\n".join(contents),
                model=ollama.OLLAMA_TEXT_MODEL,
                timeout_seconds=ollama.OLLAMA_TEXT_TIMEOUT,
            ),
            "ollama",
        )
    response, backend = generate_chat_text(system_instruction, contents)
    return iter([response] if response else []), backend


def embed_text(text: str) -> tuple[list[float], str]:
    if gemini.is_configured():
        embedding = gemini.embed_text(text)
        if embedding:
            return embedding, "gemini"
    if ollama.is_available():
        embedding = ollama.embed_text(text)
        if embedding:
            return embedding, "ollama"
    return [], "fallback"


def embed_texts(texts: list[str]) -> list[tuple[list[float], str]]:
    if not texts:
        return []
    if len(texts) == 1:
        return [embed_text(texts[0])]
    if gemini.is_configured():
        embeddings = gemini.embed_texts(texts)
        if len(embeddings) == len(texts) and all(embeddings):
            return [(embedding, "gemini") for embedding in embeddings]
    if ollama.is_available():
        embeddings = ollama.embed_texts(texts)
        if len(embeddings) == len(texts) and all(embeddings):
            return [(embedding, "ollama") for embedding in embeddings]
    return [([], "fallback") for _ in texts]


def embedding_model_name(backend: str) -> str:
    if backend == "gemini":
        return gemini.GEMINI_EMBED_MODEL
    if backend == "ollama":
        return ollama.OLLAMA_EMBED_MODEL
    return ""
