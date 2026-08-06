from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import StudentProfile, User
from analytics_app.models import AnalyzedQuestion
from chatbot.models import ChatMessage, ChatSession
from ingestion.models import ContentChunk
from learning.models import AssessmentQuestion, BaselineAssessment, Course, Material
from chatbot.services.chat_engine import _refresh_academic_discovery, _select_matches, generate_bot_response


class ChatbotFlowTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student3",
            password="password123",
            email="student3@example.com",
        )
        StudentProfile.objects.create(user=self.student, challenges="I need simpler examples.")
        self.course = Course.objects.create(code="PHY101", title="Physics")
        self.material = Material.objects.create(
            course=self.course,
            title="Newtonian Mechanics Video",
            description="Gentle explanation with worked examples.",
            source_origin=Material.SourceOrigin.EXTERNAL,
            source_type=Material.SourceType.VIDEO,
            source_provider="YouTube",
            external_url="https://www.youtube.com/watch?v=fixtureVideo123",
            is_validated=True,
        )
        assessment = BaselineAssessment.objects.create(course=self.course, title="Intro baseline")
        AssessmentQuestion.objects.create(
            assessment=assessment,
            prompt="What is the best easy way to understand Newtonian mechanics?",
            question_type="text",
        )
        prior_session = ChatSession.objects.create(student=self.student, course=self.course)
        ChatMessage.objects.create(
            session=prior_session,
            sender=ChatMessage.Sender.STUDENT,
            content="Can you suggest an easy mechanics explanation?",
        )

    @patch("chatbot.services.chat_engine._refresh_academic_discovery", return_value={"statuses": [], "material_ids": []})
    @patch("chatbot.services.chat_engine.generate_chat_text", return_value=("Start with the mechanics video first.", "gemini"))
    @patch("chatbot.services.chat_engine.backend_status", return_value={"gemini": False, "ollama": False, "ollama_models": []})
    def test_chat_page_generates_grounded_bot_reply(self, mock_backend_status, mock_generate_chat_text, mock_discovery):
        ContentChunk.objects.create(
            material=self.material,
            ordinal=0,
            text="Newtonian mechanics explains force mass and acceleration with worked examples.",
        )
        internal_material = Material.objects.create(
            course=self.course,
            title="Lecturer mechanics notes",
            description="Internal course notes",
            source_origin=Material.SourceOrigin.INTERNAL,
            source_type=Material.SourceType.FILE,
            source_provider="Uploaded by Lecturer",
            is_validated=True,
        )
        ContentChunk.objects.create(
            material=internal_material,
            ordinal=0,
            text="Mechanics force examples prepared by the lecturer.",
        )
        self.client.login(username="student3", password="password123")
        response = self.client.post(reverse("chatbot:chat"), {"message": "Explain mechanics force"}, follow=True)

        self.assertContains(response, "Start with the mechanics video first.")
        self.assertContains(response, "Materials used")
        self.assertContains(response, "Newtonian Mechanics Video")
        self.assertContains(response, "https://www.youtube-nocookie.com/embed/fixtureVideo123?rel=0")
        self.assertContains(response, "UJ Study Assistant")
        self.assertContains(response, "/static/img/uj-logo.png")
        self.assertContains(response, "Additional material")
        self.assertContains(response, "Prescribed material")
        self.assertContains(response, "Explain mechanics force", count=1)
        self.assertContains(response, "content--chat")

    @patch("chatbot.services.chat_engine._refresh_academic_discovery", return_value={"statuses": [], "material_ids": []})
    @patch("chatbot.services.chat_engine.backend_status", return_value={"gemini": False, "ollama": False, "ollama_models": []})
    def test_chat_refuses_to_answer_without_indexed_chunks(self, mock_backend_status, mock_discovery):
        self.client.login(username="student3", password="password123")
        response = self.client.post(reverse("chatbot:chat"), {"message": "Explain quantum fields"}, follow=True)

        self.assertContains(response, "I can’t answer that from the indexed course library yet")
        self.assertContains(response, "no outside knowledge was used")
        self.assertContains(response, "Additional learning material")
        self.assertContains(response, "Optional and ungraded")
        self.assertContains(response, "Additional material")
        self.assertContains(response, "youtube-nocookie.com/embed/fixtureVideo123")

    @patch("chatbot.services.chat_engine.import_curated_results")
    @patch("chatbot.services.chat_engine.discover_curated_content")
    def test_chat_discovery_invokes_academic_apis_and_persists_metadata_only(self, mock_discover, mock_import):
        cache.clear()
        mock_discover.return_value = {
            "results": [{"title": "A systems journal", "source_provider": "Crossref"}],
            "providers": [{"name": "Crossref", "status": "ok", "results": [{"title": "A systems journal"}]}],
        }
        mock_import.return_value = [self.material]

        discovery = _refresh_academic_discovery("systems thinking journals", course=self.course)

        mock_discover.assert_called_once()
        mock_import.assert_called_once_with(mock_discover.return_value, course=self.course)
        self.assertEqual(discovery["statuses"][0]["name"], "Crossref")
        self.assertEqual(discovery["statuses"][0]["count"], 1)
        self.assertEqual(discovery["material_ids"], [self.material.pk])

    @patch("chatbot.services.chat_engine.import_curated_results", side_effect=ValueError("malformed provider result"))
    @patch("chatbot.services.chat_engine.discover_curated_content")
    def test_chat_discovery_import_failure_does_not_crash_chat(self, mock_discover, mock_import):
        cache.clear()
        mock_discover.return_value = {
            "results": [{"title": "Malformed result"}],
            "providers": [{"name": "OpenAlex", "status": "ok", "results": [{"title": "Malformed result"}]}],
        }

        discovery = _refresh_academic_discovery("malformed discovery", course=self.course)

        self.assertEqual(discovery["material_ids"], [])
        self.assertEqual(discovery["statuses"][-1]["name"], "Academic discovery import")
        self.assertEqual(discovery["statuses"][-1]["status"], "unavailable")

    def test_identical_grounded_answer_uses_chunk_aware_cache(self):
        cache.clear()
        chunk = ContentChunk.objects.create(
            material=self.material,
            ordinal=0,
            text="Force equals mass times acceleration.",
        )
        session = ChatSession.objects.get(student=self.student)
        first = ChatMessage.objects.create(session=session, sender="student", content="What is force?")
        second = ChatMessage.objects.create(session=session, sender="student", content="What is force?")
        with patch("chatbot.services.chat_engine._refresh_academic_discovery", return_value={"statuses": [], "material_ids": []}), patch(
            "chatbot.services.chat_engine.generate_chat_text", return_value=("Force is grounded in the source. [Source 1]", "gemini")
        ) as mock_generate, patch("chatbot.services.chat_engine.backend_status", return_value={}):
            first_payload = generate_bot_response(first)
            second_payload = generate_bot_response(second)

        self.assertEqual(mock_generate.call_count, 1)
        self.assertEqual(first_payload["text"], second_payload["text"])
        self.assertEqual(second_payload["metadata"]["response_backend"], "gemini-cache")

    def test_select_matches_dedupes_multiple_chunks_from_same_material(self):
        first_chunk = ContentChunk.objects.create(
            material=self.material,
            ordinal=0,
            text="Feedback loops can reinforce change.",
        )
        second_chunk = ContentChunk.objects.create(
            material=self.material,
            ordinal=1,
            text="Feedback loops can also balance a system.",
        )
        matches = _select_matches(
            "feedback loops",
            [
                {"chunk": first_chunk, "material": self.material, "score": 0.9, "text": first_chunk.text},
                {"chunk": second_chunk, "material": self.material, "score": 0.8, "text": second_chunk.text},
            ],
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["material"].pk, self.material.pk)

    def test_video_query_returns_single_video_match(self):
        ContentChunk.objects.create(
            material=self.material,
            ordinal=0,
            text="Feedback loop video transcript with worked examples.",
        )
        second_video = Material.objects.create(
            course=self.course,
            title="Second Systems Video",
            source_origin=Material.SourceOrigin.EXTERNAL,
            source_type=Material.SourceType.VIDEO,
            source_provider="YouTube",
            external_url="https://www.youtube.com/watch?v=fixtureVideo456",
            is_validated=True,
        )
        second_chunk = ContentChunk.objects.create(
            material=second_video,
            ordinal=0,
            text="Another video about feedback loop dynamics.",
        )
        first_chunk = self.material.content_chunks.get(ordinal=0)

        matches = _select_matches(
            "find me videos on feedback loop",
            [
                {"chunk": first_chunk, "material": self.material, "score": 0.9, "text": first_chunk.text},
                {"chunk": second_chunk, "material": second_video, "score": 0.85, "text": second_chunk.text},
            ],
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["material"].pk, self.material.pk)

    @patch("chatbot.services.chat_engine._refresh_academic_discovery")
    @patch("chatbot.services.chat_engine.backend_status", return_value={})
    def test_unrelated_message_is_filtered_before_external_discovery(self, mock_backend, mock_discovery):
        systems_course = Course.objects.create(code="SYS100", title="Systems Thinking")
        session = ChatSession.objects.create(student=self.student, course=systems_course, title="Systems chat")
        message = ChatMessage.objects.create(session=session, sender="student", content="What is today's weather?")

        payload = generate_bot_response(message)

        self.assertTrue(payload["metadata"]["analytics_filtered"])
        self.assertIn("automatically filtered", payload["text"])
        self.assertFalse(AnalyzedQuestion.objects.filter(message=message).exists())
        mock_discovery.assert_not_called()

# Create your tests here.
