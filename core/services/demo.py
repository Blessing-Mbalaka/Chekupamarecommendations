from accounts.models import User, UserRole
from learning.models import AssessmentQuestion, BaselineAssessment, Course, LecturerPrompt, Material, Topic

from .warmup import warmup_systems_thinking_cache


CURATED_SYSTEMS_THINKING_VIDEOS = [
    {
        "video_id": "-sfiReUu3o0",
        "title": "Systems Thinking: A Little Film About a Big Idea",
        "provider": "YouTube · Cabrera Research Lab",
        "description": (
            "An award-winning introduction to DSRP systems thinking from Cabrera Research Lab, "
            "a research lab born at Cornell University."
        ),
        "tags": "systems thinking, DSRP, mental models, relationships, perspectives",
        "citation": "https://www.cabreralab.science/publications",
    },
    {
        "video_id": "lpIxTHmiLTE",
        "title": "Becoming a Systems Thinker: Big-Picture Thinking and Consequences",
        "provider": "YouTube · IIT Madras",
        "description": (
            "An IIT Madras BS programme lecture on big-picture thinking, consequences of actions, "
            "holistic analysis, and systems-aware decision-making."
        ),
        "tags": "systems thinking, big picture, consequences, holistic analysis, problem solving",
        "citation": "https://study.iitm.ac.in/ds/",
    },
    {
        "video_id": "yYyTUs9ipmc",
        "title": "An Introduction to Systems Thinking by Gerald Midgley",
        "provider": "YouTube · Integration and Implementation Sciences",
        "description": (
            "A university-level introduction by Professor Gerald Midgley of the Centre for Systems "
            "Studies, University of Hull, recorded for the i2S conference."
        ),
        "tags": "systems thinking, wicked problems, boundaries, complexity, systemic intervention",
        "citation": "https://i2s.anu.edu.au/resources/featuring-two-most-popular-videos-by-george-richardson-and-gerald-midgley/",
    },
    {
        "video_id": "Hm_UjbsHReI",
        "title": "Systems Thinking in Action with Professor Gerald Midgley",
        "provider": "YouTube · Manaaki Whenua Landcare Research",
        "description": (
            "Professor Gerald Midgley of the University of Hull introduces systems thinking in action "
            "for Manaaki Whenua, New Zealand's Crown Research Institute for land and environment."
        ),
        "tags": "systems thinking, systems in action, wicked problems, research, intervention",
        "citation": "https://integrated.landcareresearch.co.nz/resources/systems-thinking.html",
    },
]


def seed_curated_systems_videos(course, lecturer, topic=None):
    # Remove the historical demo-only rickroll without touching unrelated user data.
    Material.objects.filter(course=course, source_record_id="dQw4w9WgXcQ").delete()
    curated_ids = {item["video_id"] for item in CURATED_SYSTEMS_THINKING_VIDEOS}
    Material.objects.filter(
        course=course,
        source_endpoint="curated systems-thinking starter library",
    ).exclude(source_record_id__in=curated_ids).delete()
    materials = []
    for item in CURATED_SYSTEMS_THINKING_VIDEOS:
        video_url = f"https://www.youtube.com/watch?v={item['video_id']}"
        material, _ = Material.objects.update_or_create(
            course=course,
            source_record_id=item["video_id"],
            defaults={
                "topic": topic,
                "title": item["title"],
                "description": item["description"],
                "source_origin": Material.SourceOrigin.EXTERNAL,
                "source_type": Material.SourceType.VIDEO,
                "source_provider": item["provider"],
                "source_endpoint": "curated systems-thinking starter library",
                "external_url": video_url,
                "original_source_url": video_url,
                "youtube_title": item["title"],
                "tags": item["tags"],
                "source_citation": item["citation"],
                "is_validated": True,
                "uploaded_by": lecturer,
            },
        )
        materials.append(material)
    return materials


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

    seed_curated_systems_videos(course, lecturer, topic=topic_feedback)

    warmed_entries = warmup_systems_thinking_cache()
    return {
        "course": course.code,
        "users": ["demo_student", "demo_ta", "demo_lecturer"],
        "warmup_entries": len(warmed_entries),
    }
