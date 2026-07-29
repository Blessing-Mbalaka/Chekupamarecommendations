from learning.models import LecturerPrompt
from recommendations.services.engine import recommend_for_student, store_recommendations
from recommendations.services.gemini import generate_text, is_configured

from chatbot.models import ChatMessage


def generate_bot_response(message: ChatMessage):
    session = message.session
    student = session.student
    lecturer_prompt = (
        LecturerPrompt.objects.filter(course=session.course, is_active=True).order_by("title").first()
        if session.course
        else None
    )
    recommendations = recommend_for_student(
        student=student,
        course=session.course,
        query_text=message.content,
        limit=3,
    )
    store_recommendations(student, recommendations, related_message=message)

    challenge_text = getattr(getattr(student, "student_profile", None), "challenges", "")
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
            challenge_line,
            prompt_line,
            recommendation_line,
            "If you want, ask me for a quiz, a simpler explanation, or the best item to download first.",
        ]
    )

    if not is_configured():
        return fallback

    system_instruction = (
        "You are a study support chatbot. Keep answers concise, supportive, and personalized. "
        "Use the supplied student context and recommendations. Distinguish internal uploaded materials "
        "from external API or web sources. When videos are recommended, mention they can be embedded in the UI."
    )
    contents = [
        f"Student message: {message.content}",
        f"Student challenge context: {challenge_line}",
        f"Lecturer context: {prompt_line}",
        f"Recommendation context: {recommendation_line}",
        "Respond with practical guidance and mention what material to open first.",
    ]
    return generate_text(system_instruction, contents) or fallback
