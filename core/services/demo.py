from accounts.models import User, UserRole
from learning.models import AssessmentQuestion, BaselineAssessment, Course, LecturerPrompt, Material, Topic

from .warmup import warmup_systems_thinking_cache


def bootstrap_demo_data():
    lecturer, _ = User.objects.update_or_create(
        username="demo_lecturer",
        defaults={
            "email": "demo_lecturer@example.com",
            "role": UserRole.LECTURER,
            "first_name": "Demo",
            "last_name": "Lecturer",
        },
    )
    lecturer.set_password("Password123!")
    lecturer.save()

    ta, _ = User.objects.update_or_create(
        username="demo_ta",
        defaults={
            "email": "demo_ta@example.com",
            "role": UserRole.TA,
            "first_name": "Demo",
            "last_name": "Assistant",
        },
    )
    ta.set_password("Password123!")
    ta.save()

    student, _ = User.objects.update_or_create(
        username="demo_student",
        defaults={
            "email": "demo_student@example.com",
            "role": UserRole.STUDENT,
            "first_name": "Demo",
            "last_name": "Student",
        },
    )
    student.set_password("Password123!")
    student.save()

    course, _ = Course.objects.get_or_create(
        code="SYS101",
        defaults={
            "title": "Systems Thinking Foundations",
            "description": "Introductory systems thinking, causal loops, feedback, delays, and policy resistance.",
        },
    )
    course.lecturers.add(lecturer)
    course.teaching_assistants.add(ta)
    course.students.add(student)

    topic_feedback, _ = Topic.objects.get_or_create(
        course=course,
        title="Feedback Loops",
        defaults={"description": "Reinforcing and balancing loops in complex systems."},
    )
    topic_delays, _ = Topic.objects.get_or_create(
        course=course,
        title="Delays and Unintended Consequences",
        defaults={"description": "How lag and side effects shape system outcomes."},
    )

    assessment, _ = BaselineAssessment.objects.get_or_create(
        course=course,
        title="Systems Thinking Baseline",
        defaults={"description": "Warmup questions covering feedback, delays, and leverage points."},
    )

    questions = [
        {
            "prompt": "Which loop counteracts change and pushes a system toward stability?",
            "topic": topic_feedback,
            "question_type": AssessmentQuestion.QuestionType.MULTIPLE_CHOICE,
            "options": ["Balancing loop", "Reinforcing loop", "Chaotic loop"],
            "correct_option": "Balancing loop",
            "order": 1,
        },
        {
            "prompt": "Name one risk of introducing a policy without considering system delays.",
            "topic": topic_delays,
            "question_type": AssessmentQuestion.QuestionType.SHORT_TEXT,
            "expected_keywords": "unintended consequences, overreaction, delay, side effects",
            "order": 2,
        },
        {
            "prompt": "A loop that amplifies growth is called what?",
            "topic": topic_feedback,
            "question_type": AssessmentQuestion.QuestionType.MULTIPLE_CHOICE,
            "options": ["Balancing loop", "Reinforcing loop", "Linear loop"],
            "correct_option": "Reinforcing loop",
            "order": 3,
        },
    ]
    for payload in questions:
        AssessmentQuestion.objects.update_or_create(
            assessment=assessment,
            prompt=payload["prompt"],
            defaults=payload,
        )

    LecturerPrompt.objects.update_or_create(
        course=course,
        title="Systems Thinking Study Coach",
        defaults={
            "prompt_text": "Guide students toward causal loops, leverage points, feedback, and unintended consequences using clear beginner language.",
            "is_active": True,
            "created_by": lecturer,
        },
    )

    Material.objects.update_or_create(
        course=course,
        title="Orange Systems Thinking Starter Notes",
        defaults={
            "description": "Internal summary notes on leverage points, balancing loops, reinforcing loops, and system archetypes.",
            "source_origin": Material.SourceOrigin.INTERNAL,
            "source_type": Material.SourceType.FILE,
            "source_provider": "Uploaded by Lecturer",
            "source_endpoint": "internal upload",
            "source_record_id": "sys101-internal-notes",
            "is_validated": True,
            "uploaded_by": lecturer,
        },
    )

    Material.objects.update_or_create(
        course=course,
        title="Systems Thinking Overview Video",
        defaults={
            "description": "Manual embedded video placeholder for systems thinking orientation.",
            "source_origin": Material.SourceOrigin.EXTERNAL,
            "source_type": Material.SourceType.VIDEO,
            "source_provider": "YouTube",
            "source_endpoint": "manual embed",
            "source_record_id": "dQw4w9WgXcQ",
            "external_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "original_source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "youtube_title": "Systems Thinking Overview Video",
            "is_validated": True,
            "uploaded_by": lecturer,
        },
    )

    warmed_entries = warmup_systems_thinking_cache()
    return {
        "course": course.code,
        "users": ["demo_student", "demo_ta", "demo_lecturer"],
        "warmup_entries": len(warmed_entries),
    }
