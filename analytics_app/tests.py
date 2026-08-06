from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from chatbot.models import ChatMessage, ChatSession
from learning.models import Course, Topic

from .models import AnalyzedQuestion, QuestionTheme
from .services.questions import classify_systems_question, record_relevant_question, suggest_question_themes


class QuestionClassificationTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="student-a", email="student-a@example.com", password="pass")
        self.course = Course.objects.create(code="SYS101", title="Systems Thinking")
        self.session = ChatSession.objects.create(student=self.student, course=self.course)

    def test_noise_and_off_topic_questions_are_not_stored(self):
        for text in ("hi", "what is the weather today?"):
            message = ChatMessage.objects.create(session=self.session, sender="student", content=text)
            classification = classify_systems_question(text, course=self.course, use_llm=False)
            self.assertFalse(classification["relevant"])
            self.assertIsNone(record_relevant_question(message, classification, course=self.course))
        self.assertEqual(AnalyzedQuestion.objects.count(), 0)

    def test_systems_question_is_stored_once(self):
        message = ChatMessage.objects.create(
            session=self.session,
            sender="student",
            content="How do reinforcing feedback loops affect a complex system?",
        )
        classification = classify_systems_question(message.content, course=self.course, use_llm=False)
        first = record_relevant_question(message, classification, course=self.course)
        second = record_relevant_question(message, classification, course=self.course)
        self.assertTrue(classification["relevant"])
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(AnalyzedQuestion.objects.count(), 1)

    @patch("analytics_app.services.questions.extract_themes")
    def test_topic_model_suggests_editable_theme_and_assignment(self, mock_extract):
        message = ChatMessage.objects.create(session=self.session, sender="student", content="Explain feedback loops in systems.")
        question = record_relevant_question(
            message,
            classify_systems_question(message.content, course=self.course, use_llm=False),
            course=self.course,
        )
        mock_extract.return_value = ([{"label": "Feedback Loops", "keywords": ["feedback", "loop"]}], [[0.91]], "lda")
        themes, backend, report = suggest_question_themes(self.course, count=3, model="lda", created_by=self.student)
        question.refresh_from_db()
        self.assertEqual(backend, "lda")
        self.assertTrue(themes[0].is_model_suggested)
        self.assertEqual(question.theme, themes[0])
        self.assertEqual(report["theme_labels"], [themes[0].label])

    @patch("analytics_app.services.questions.extract_themes")
    def test_topic_model_replaces_material_type_labels_with_cluster_topic(self, mock_extract):
        Topic.objects.create(course=self.course, title="Feedback Loops")
        message = ChatMessage.objects.create(session=self.session, sender="student", content="Please provide videos on feedback loops")
        question = record_relevant_question(
            message,
            classify_systems_question(message.content, course=self.course, use_llm=False),
            course=self.course,
        )
        mock_extract.return_value = ([{"label": "Videos", "keywords": ["videos"]}], [[1.0]], "lda-distinctive")

        themes, backend, _ = suggest_question_themes(self.course, count=3, model="lda", created_by=self.student)

        question.refresh_from_db()
        self.assertEqual(backend, "lda-distinctive")
        self.assertEqual(themes[0].label, "Feedback Loops")
        self.assertEqual(question.suggested_theme_label, "Feedback Loops")

    def test_topic_model_form_can_use_kmeans_choice(self):
        message = ChatMessage.objects.create(session=self.session, sender="student", content="Explain feedback loops in systems.")
        record_relevant_question(
            message,
            classify_systems_question(message.content, course=self.course, use_llm=False),
            course=self.course,
        )

        themes, backend, report = suggest_question_themes(self.course, count=2, model="kmeans", created_by=self.student)

        self.assertTrue(themes)
        self.assertIn(backend, {"kmeans", "lda", "keyword-fallback"})
        self.assertEqual(report["requested_model"], "kmeans")


class QuestionAnalyticsViewTests(TestCase):
    def setUp(self):
        self.lecturer = User.objects.create_user(
            username="lecturer-a", email="lecturer-a@example.com", password="pass", role="lecturer"
        )
        self.student = User.objects.create_user(username="student-b", email="student-b@example.com", password="pass")
        self.course = Course.objects.create(code="SYS201", title="Applied Systems Thinking")
        self.course.lecturers.add(self.lecturer)
        session = ChatSession.objects.create(student=self.student, course=self.course)
        message = ChatMessage.objects.create(session=session, sender="student", content="What is a leverage point in a system?")
        self.question = AnalyzedQuestion.objects.create(message=message, course=self.course, text=message.content)

    def test_student_cannot_open_lecturer_analytics(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("analytics_app:questions"))
        self.assertEqual(response.status_code, 403)

    def test_lecturer_can_view_and_manually_code_question(self):
        self.client.force_login(self.lecturer)
        response = self.client.post(
            reverse("analytics_app:theme_create"),
            {"course": self.course.pk, "label": "Leverage points", "description": "Intervention themes"},
        )
        self.assertRedirects(response, reverse("analytics_app:questions"))
        theme = QuestionTheme.objects.get(label="Leverage points")
        response = self.client.post(
            reverse("analytics_app:questions"),
            {"action": "assign_theme", "question_id": self.question.pk, "theme_id": theme.pk},
        )
        self.assertRedirects(response, reverse("analytics_app:questions"))
        self.question.refresh_from_db()
        self.assertEqual(self.question.theme, theme)
        page = self.client.get(reverse("analytics_app:questions"))
        self.assertContains(page, "Question Analytics")
        self.assertContains(page, "What is a leverage point")

    @patch("analytics_app.views.suggest_question_themes")
    def test_lecturer_sees_model_specific_theme_report(self, mock_suggest):
        mock_suggest.return_value = (
            [object()],
            "kmeans",
            {
                "requested_model": "kmeans",
                "backend": "kmeans",
                "requested_count": 3,
                "document_count": 4,
                "theme_labels": ["Feedback Loops"],
                "keywords": [{"label": "Feedback Loops", "keywords": ["feedback loops", "reinforcing loop"]}],
                "metric_label": "Inertia by K (lower is tighter)",
                "k_curve": [{"k": 2, "score": 1.5}, {"k": 3, "score": 1.1}],
            },
        )

        self.client.force_login(self.lecturer)
        response = self.client.post(
            reverse("analytics_app:questions"),
            {"action": "suggest_themes", "course": self.course.pk, "model": "kmeans", "theme_count": 3},
            follow=True,
        )

        self.assertContains(response, "Inertia by K (lower is tighter)")
        self.assertContains(response, "Feedback Loops")
        self.assertContains(response, "used KMEANS")
