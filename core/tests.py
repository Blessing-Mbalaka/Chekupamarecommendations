from django.test import TestCase
from django.urls import reverse
from tempfile import TemporaryDirectory
from unittest.mock import patch

from accounts.models import User
from chatbot.models import ChatMessage, ChatSession
from core.services.temp_functions.commonquestions import (
    COMMON_QUESTIONS_INDEX_CACHE_KEY,
    FALLBACK_COMMON_QUESTIONS,
    extract_common_questions,
    load_common_questions,
    warm_common_question_cache,
)
from learning.models import BaselineAssessment, Course, Material, Topic
from recommendations.models import Recommendation
from core.services.demo import CURATED_SYSTEMS_THINKING_VIDEOS, seed_curated_systems_videos
from django.core.cache import cache
from pathlib import Path


class DashboardTests(TestCase):
    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_renders_for_authenticated_user(self):
        user = User.objects.create_user(
            username="student4",
            password="password123",
            email="student4@example.com",
        )
        self.client.login(username="student4", password="password123")
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your learning hub")

    def test_dashboard_recommendation_renders_as_flip_card(self):
        user = User.objects.create_user(username="flip_student", password="password123")
        course = Course.objects.create(code="SYS201", title="Applied Systems")
        material = Material.objects.create(course=course, title="Feedback Loop Guide", is_validated=True)
        BaselineAssessment.objects.create(course=course, title="Applied Systems Baseline")
        Recommendation.objects.create(
            student=user,
            material=material,
            reason="Recommended for your current study goals.",
            score=3,
        )
        self.client.login(username="flip_student", password="password123")

        response = self.client.get(reverse("core:dashboard"))

        self.assertContains(response, "recommendation-flip--hint")
        self.assertContains(response, "Feedback Loop Guide")
        self.assertContains(response, "View options")
        self.assertContains(response, "Study with assistant")
        self.assertContains(response, "Available materials")
        self.assertContains(response, "Baseline assessments")
        self.assertContains(response, "Courses")
        self.assertContains(response, 'data-flip-card style', count=4)
        self.assertContains(response, "dashboard-static-tile")

    def test_health_console_denies_student(self):
        user = User.objects.create_user(
            username="student_health",
            password="password123",
            email="student_health@example.com",
            role="student",
        )
        self.client.login(username="student_health", password="password123")
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 403)

    def test_health_console_allows_ta(self):
        user = User.objects.create_user(
            username="ta_user",
            password="password123",
            email="ta@example.com",
            role="ta",
        )
        self.client.login(username="ta_user", password="password123")
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "API and chatbot health")

    def test_curation_portal_shows_stats_for_superuser(self):
        superuser = User.objects.create_superuser(
            username="portal_admin",
            password="password123",
            email="portal@example.com",
        )
        course = Course.objects.create(code="SYS101", title="Systems Thinking")
        Material.objects.create(course=course, title="Internal guide", is_validated=True)
        session = ChatSession.objects.create(student=superuser, course=course)
        ChatMessage.objects.create(
            session=session,
            sender=ChatMessage.Sender.STUDENT,
            content="How do feedback loops work?",
        )
        self.client.login(username="portal_admin", password="password123")
        response = self.client.get(reverse("core:curation_portal"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student Questions")
        self.assertContains(response, "Upload")
        self.assertContains(response, "Discovery")

    def test_curated_video_seed_replaces_historical_placeholder(self):
        lecturer = User.objects.create_user(username="seed_lecturer", password="password123", role="lecturer")
        course = Course.objects.create(code="SEED101", title="Systems Thinking")
        topic = Topic.objects.create(course=course, title="Feedback Loops")
        Material.objects.create(
            course=course,
            title="Old placeholder",
            source_type=Material.SourceType.VIDEO,
            source_record_id="dQw4w9WgXcQ",
            external_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )

        videos = seed_curated_systems_videos(course, lecturer, topic)

        self.assertEqual(len(videos), len(CURATED_SYSTEMS_THINKING_VIDEOS))
        self.assertFalse(Material.objects.filter(course=course, source_record_id="dQw4w9WgXcQ").exists())
        self.assertTrue(all(video.is_validated for video in videos))
        self.assertTrue(all("YouTube ·" in video.source_provider for video in videos))


class CommonQuestionWarmupTests(TestCase):
    def test_extract_common_questions_ignores_following_table_content(self):
        markdown_text = """
**Section 1: Systems Thinking & Causal Loop Diagrams (CLDs)**

1. **Develop**
   individual Causal Loop Diagrams using Vensim.

**Step 5: Architecture Development**

1. **Develop**
   a comprehensive System Architecture using the format below:

   **System Element**
   Categories of People
   Physical / Digital Type

2. **Explain**
   how weaknesses in physical infrastructure propagate through processes.
"""

        questions = extract_common_questions(markdown_text)

        self.assertEqual(
            [entry["question"] for entry in questions],
            [
                "Develop individual Causal Loop Diagrams using Vensim.",
                "Develop a comprehensive System Architecture using the format below",
                "Explain how weaknesses in physical infrastructure propagate through processes.",
            ],
        )
        self.assertEqual(questions[0]["section"], "Section 1: Systems Thinking & Causal Loop Diagrams (CLDs)")
        self.assertEqual(questions[1]["step"], "Step 5: Architecture Development")

    def test_load_common_questions_uses_fallback_when_default_file_is_empty(self):
        with TemporaryDirectory() as temp_dir:
            question_file = Path(temp_dir) / "common questions.md"
            question_file.write_text("", encoding="utf-8")
            with patch("core.services.temp_functions.commonquestions.DEFAULT_COMMON_QUESTIONS_PATH", question_file):
                questions = load_common_questions()

        self.assertEqual(questions, FALLBACK_COMMON_QUESTIONS)

    @patch("core.services.temp_functions.commonquestions.generate_grounded_response_for_query")
    def test_warm_common_question_cache_stores_payloads(self, mock_generate):
        cache.clear()
        mock_generate.return_value = {
            "text": "Grounded answer",
            "metadata": {
                "grounded": True,
                "sources": [{"title": "Indexed source"}],
                "external_suggestions": [{"title": "External suggestion"}],
            },
        }

        with TemporaryDirectory() as temp_dir:
            question_file = Path(temp_dir) / "common.md"
            question_file.write_text("1. First question?\n\n2. Second question?\n", encoding="utf-8")

            warmed_entries = warm_common_question_cache(path=question_file, limit=1)

        self.assertEqual(len(warmed_entries), 1)
        self.assertEqual(warmed_entries[0]["question"], "First question?")
        self.assertEqual(warmed_entries[0]["source_count"], 1)
        self.assertEqual(warmed_entries[0]["external_suggestion_count"], 1)
        mock_generate.assert_called_once_with("First question?", course=None)

        cached_keys = cache.get(COMMON_QUESTIONS_INDEX_CACHE_KEY)
        self.assertEqual(cached_keys, [warmed_entries[0]["cache_key"]])
        cached_entry = cache.get(warmed_entries[0]["cache_key"])
        self.assertEqual(cached_entry["payload"]["text"], "Grounded answer")
