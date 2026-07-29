from recommendations.services.llm import backend_status
from ingestion.services.providers import provider_health


def chatbot_health_snapshot():
    llm_status = backend_status()
    items = [
        {
            "name": "Gemini",
            "status": "configured" if llm_status["gemini"] else "missing_key",
            "detail": "Generative and embedding backend",
        },
        {
            "name": "Ollama",
            "status": "ok" if llm_status["ollama"] else "unavailable",
            "detail": ", ".join(llm_status["ollama_models"]) if llm_status["ollama_models"] else "No local models detected",
        },
    ]
    return {
        "chatbot": items,
        "providers": provider_health(),
    }
