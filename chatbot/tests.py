import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import StudentProfile, User
from analytics_app.models import AnalyzedQuestion
from chatbot.models import ChatMessage, ChatSession
from core.services.temp_functions.commonquestions import (
    COMMON_QUESTIONS_INDEX_CACHE_KEY,
)
from ingestion.models import ContentChunk
from learning.models import AssessmentQuestion, BaselineAssessment, Course, Material
from chatbot.services.chat_engine import (
    _refresh_academic_discovery,
    _select_matches,
    generate_bot_response,
    generate_grounded_response_for_query,
    stream_bot_response,
)


class ChatbotFlowTests(TestCase):
    def setUp(self):
        cache.clear()
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

    def _cache_course_faq(self):
        cache_key = "common-questions-warmup:chat-priority"
        cache.set(
            cache_key,
            {
                "question": "How does force relate to mass and acceleration?",
                "section": "Mechanics",
                "step": "",
                "course_id": self.course.pk,
                "embedding": [1.0, 0.0],
                "embedding_backend": "test",
                "payload": {
                    "text": "Force equals mass multiplied by acceleration.",
                    "metadata": {
                        "rag_only": True,
                        "grounded": True,
                        "response_backend": "gemini",
                        "sources": [],
                        "external_suggestions": [],
                        "provider_statuses": [],
                    },
                },
            },
        )
        cache.set(COMMON_QUESTIONS_INDEX_CACHE_KEY, [cache_key])

    @patch("core.services.temp_functions.commonquestions.embed_text", return_value=([0.99, 0.01], "test"))
    @patch("chatbot.services.chat_engine.retrieve_chunks", side_effect=AssertionError("RAG should not run for an FAQ hit"))
    def test_semantic_faq_match_is_checked_before_rag(self, mock_retrieve, mock_embed):
        cache.clear()
        self._cache_course_faq()
        session = ChatSession.objects.get(student=self.student)
        message = ChatMessage.objects.create(
            session=session,
            sender=ChatMessage.Sender.STUDENT,
            content="Can you explain the connection between acceleration, mass, and force?",
        )

        payload = generate_bot_response(message)

        self.assertEqual(payload["text"], "Force equals mass multiplied by acceleration.")
        self.assertEqual(payload["metadata"]["response_backend"], "faq-cache")
        self.assertEqual(
            payload["metadata"]["faq_match"]["question"],
            "How does force relate to mass and acceleration?",
        )
        self.assertTrue(AnalyzedQuestion.objects.filter(message=message).exists())

    @patch("core.services.temp_functions.commonquestions.embed_text", return_value=([0.99, 0.01], "test"))
    @patch("chatbot.services.chat_engine.retrieve_chunks", side_effect=AssertionError("RAG should not run for an FAQ hit"))
    def test_streaming_faq_match_emits_cached_answer_without_rag(self, mock_retrieve, mock_embed):
        cache.clear()
        self._cache_course_faq()
        session = ChatSession.objects.get(student=self.student)
        message = ChatMessage.objects.create(
            session=session,
            sender=ChatMessage.Sender.STUDENT,
            content="What links mass and acceleration to force?",
        )

        events = list(stream_bot_response(message))

        self.assertEqual(events[-2], {"type": "token", "text": "Force equals mass multiplied by acceleration."})
        self.assertEqual(events[-1]["type"], "complete")
        self.assertEqual(events[-1]["payload"]["metadata"]["response_backend"], "faq-cache")

    @patch("core.services.temp_functions.commonquestions.embed_text", return_value=([1.0, 0.0], "test"))
    @patch("chatbot.services.chat_engine._refresh_academic_discovery", return_value={"statuses": [], "material_ids": []})
    @patch("chatbot.services.chat_engine.generate_chat_text", return_value=("Refreshed from current material.", "test"))
    def test_rag_only_generation_bypasses_existing_faq_cache(self, mock_generate, mock_discovery, mock_embed):
        self._cache_course_faq()
        chunk = ContentChunk.objects.create(
            material=self.material,
            ordinal=0,
            text="Current material about force, mass, and acceleration.",
            embedding=[1.0, 0.0],
        )
        with patch(
            "chatbot.services.chat_engine.retrieve_chunks",
            return_value=[
                {
                    "chunk": chunk,
                    "material": self.material,
                    "score": 1.0,
                    "semantic_score": 1.0,
                    "bm25_score": 1.0,
                    "text": chunk.text,
                }
            ],
        ):
            payload = generate_grounded_response_for_query(
                "How does force relate to mass and acceleration?",
                course=self.course,
                use_faq_cache=False,
            )

        self.assertEqual(payload["text"], "Refreshed from current material.")
        self.assertEqual(payload["metadata"]["response_backend"], "test")

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
        self.assertContains(response, "data-render-markdown")
        self.assertContains(response, "mathjax@3.2.2")
        self.assertContains(response, "data-stream-url")

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

    def test_saved_chat_does_not_render_material_that_is_still_pending(self):
        self.material.is_validated = False
        self.material.save(update_fields=["is_validated"])
        session = ChatSession.objects.get(student=self.student)
        ChatMessage.objects.create(
            session=session,
            sender=ChatMessage.Sender.BOT,
            content="I found a possible external resource.",
            metadata={
                "external_suggestions": [
                    {
                        "material_id": self.material.pk,
                        "title": self.material.title,
                        "external_url": self.material.external_url,
                    }
                ]
            },
        )
        self.client.login(username=self.student.username, password="password123")

        response = self.client.get(reverse("chatbot:chat"))

        self.assertNotContains(response, self.material.title)

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

    def test_select_matches_keeps_two_distant_passages_from_same_material(self):
        first_chunk = ContentChunk.objects.create(
            material=self.material,
            ordinal=0,
            text="Feedback loops can reinforce change.",
        )
        distant_chunk = ContentChunk.objects.create(
            material=self.material,
            ordinal=5,
            text="System boundaries determine what an analysis includes.",
        )
        matches = _select_matches(
            "feedback loops and boundaries",
            [
                {"chunk": first_chunk, "material": self.material, "score": 0.9, "text": first_chunk.text},
                {"chunk": distant_chunk, "material": self.material, "score": 0.8, "text": distant_chunk.text},
            ],
        )

        self.assertEqual(len(matches), 2)

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

    @patch("chatbot.views.stream_bot_response")
    def test_stream_endpoint_persists_completed_answer(self, mock_stream):
        mock_stream.return_value = iter(
            [
                {"type": "status", "text": "Searching…"},
                {"type": "token", "text": "**Feedback**"},
                {
                    "type": "complete",
                    "payload": {
                        "text": "**Feedback**",
                        "metadata": {
                            "rag_only": True,
                            "grounded": True,
                            "response_backend": "ollama",
                            "sources": [
                                {
                                    "number": 1,
                                    "material_id": self.material.pk,
                                    "title": self.material.title,
                                    "display_label": self.material.title,
                                    "score": 0.91,
                                    "url": self.material.get_absolute_url(),
                                    "external_url": self.material.external_url,
                                    "preview_kind": "video",
                                    "preview_url": self.material.embed_url,
                                    "provider": "YouTube",
                                    "source_type": "Video",
                                    "authors": "",
                                    "publication": "",
                                    "topics": [],
                                    "origin": "external",
                                    "origin_label": "Additional material",
                                }
                            ],
                            "external_suggestions": [],
                            "provider_statuses": [],
                        },
                    },
                },
            ]
        )
        self.client.login(username="student3", password="password123")

        response = self.client.post(
            reverse("chatbot:chat_stream"),
            {"message": "Explain feedback"},
        )
        body = b"".join(response.streaming_content).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "token"', body)
        self.assertIn('"type": "done"', body)
        done_event = next(
            json.loads(line)
            for line in body.splitlines()
            if json.loads(line).get("type") == "done"
        )
        self.assertIn("source-preview--video", done_event["extras_html"])
        self.assertIn("youtube-nocookie.com/embed/fixtureVideo123", done_event["extras_html"])
        self.assertTrue(
            ChatMessage.objects.filter(
                session__student=self.student,
                sender=ChatMessage.Sender.BOT,
                content="**Feedback**",
            ).exists()
        )

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
