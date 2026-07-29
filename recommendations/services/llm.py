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


def backend_status():
    return {
        "gemini": gemini.is_configured(),
        "ollama": ollama.is_available(),
        "ollama_models": [model.get("name", "") for model in ollama.list_models()],
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
        refined = ollama.generate_text(system_instruction, prompt)
        if refined:
            return refined.strip(), "ollama"
    return student_message.strip(), "fallback"


def generate_chat_text(system_instruction: str, contents: list[str]) -> tuple[str, str]:
    if gemini.is_configured():
        response = gemini.generate_text(system_instruction, contents)
        if response:
            return response, "gemini"
    if ollama.is_available():
        response = ollama.generate_text(system_instruction, "\n".join(contents))
        if response:
            return response, "ollama"
    return "", "fallback"


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
