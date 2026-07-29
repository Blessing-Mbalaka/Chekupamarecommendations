from ingestion.services.providers import discover_external_content, persist_external_results
from learning.models import LecturerPrompt
from recommendations.services.engine import recommend_for_student, store_recommendations
from recommendations.services.llm import backend_status, generate_chat_text, refine_search_query

from chatbot.models import ChatMessage


def generate_bot_response(message: ChatMessage):
    session = message.session
    student = session.student
    lecturer_prompt = (
        LecturerPrompt.objects.filter(course=session.course, is_active=True).order_by("title").first()
        if session.course
        else None
    )
    challenge_text = getattr(getattr(student, "student_profile", None), "challenges", "")
    lecturer_text = lecturer_prompt.prompt_text if lecturer_prompt else ""
    refined_query, query_backend = refine_search_query(message.content, challenge_text, lecturer_text)
    discovery_payload = discover_external_content(refined_query, limit_per_provider=2)
    external_materials = persist_external_results(
        discovery_payload,
        course=session.course,
        uploaded_by=student,
    ) if session.course else []
    recommendations = recommend_for_student(
        student=student,
        course=session.course,
        query_text=refined_query or message.content,
        limit=3,
        use_semantic=False,
        generate_missing_embeddings=False,
    )
    store_recommendations(student, recommendations, related_message=message)

    challenge_line = (
        f"I've factored in your shared challenges: {challenge_text[:180]}."
        if challenge_text
        else "I can personalize better once your challenges are filled in on your profile."
    )
    prompt_line = (
        f"Lecturer focus for this course: {lecturer_prompt.prompt_text[:180]}."
        if lecturer_prompt
        else "No lecturer prompt is active yet, so I am leaning on your baseline and current question."
    )

    if recommendations:
        recommendation_lines = []
        for item in recommendations:
            recommendation_lines.append(
                f"{item.title} [{item.get_source_origin_display()} / {item.get_source_type_display()}]"
            )
        recommendation_line = "Recommended next resources: " + "; ".join(recommendation_lines) + "."
    else:
        recommendation_line = "I do not have a strong resource match yet, so start by completing the baseline and profile."

    fallback = " ".join(
        [
            "Here is a personalized study direction based on your question.",
            f"Refined search string: {refined_query}.",
            challenge_line,
            prompt_line,
            recommendation_line,
            "If you want, ask me for a quiz, a simpler explanation, or the best item to download first.",
        ]
    )

    system_instruction = (
        "You are a study support chatbot. Keep answers concise, supportive, and personalized. "
        "Use the supplied student context and recommendations. Distinguish internal uploaded materials "
        "from external API or web sources. When videos are recommended, mention they can be embedded in the UI."
    )
    contents = [
        f"Student message: {message.content}",
        f"Refined academic search string: {refined_query}",
        f"Student challenge context: {challenge_line}",
        f"Lecturer context: {prompt_line}",
        f"Recommendation context: {recommendation_line}",
        f"External provider statuses: {discovery_payload['providers']}",
        "Respond with practical guidance and mention what material to open first.",
    ]
    generated_text, response_backend = generate_chat_text(system_instruction, contents)
    return {
        "text": generated_text or fallback,
        "metadata": {
            "refined_query": refined_query,
            "query_backend": query_backend,
            "response_backend": response_backend,
            "provider_statuses": discovery_payload["providers"],
            "ollama_status": backend_status(include_models=False),
        },
    }
