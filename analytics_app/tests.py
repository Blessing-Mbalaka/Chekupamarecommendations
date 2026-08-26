import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from chatbot.models import ChatMessage, ChatSession
from learning.models import Course, Material, Topic

from .models import (
    AnalyticsEvent,
    AnalyticsQuestion,
    AnalyticsQuestionnaire,
    AnalyticsQuestionnaireResponse,
    AnalyzedQuestion,
    QuestionTheme,
)
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

    def test_analysis_is_preserved_when_source_message_is_deleted(self):
        message = ChatMessage.objects.create(
            session=self.session,
            sender="student",
            content="How do reinforcing feedback loops affect a complex system?",
        )
        question = record_relevant_question(
            message,
            classify_systems_question(message.content, course=self.course, use_llm=False),
            course=self.course,
        )

        message.delete()

        question.refresh_from_db()
        self.assertIsNone(question.message)
        self.assertEqual(question.text, "How do reinforcing feedback loops affect a complex system?")

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


class SiteAnalyticsTests(TestCase):
    def setUp(self):
        self.lecturer = User.objects.create_user(
            username="analytics-lecturer", email="analytics-lecturer@example.com", password="pass", role="lecturer"
        )
        self.student = User.objects.create_user(
            username="analytics-student", email="analytics-student@example.com", password="pass", role="student"
        )
        self.outside_student = User.objects.create_user(
            username="outside-student", email="outside-student@example.com", password="pass", role="student"
        )
        self.course = Course.objects.create(code="ANA101", title="Analytics")
        self.course.lecturers.add(self.lecturer)
        self.course.students.add(self.student)

    def test_student_cannot_open_site_analytics(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("analytics_app:site"))
        self.assertEqual(response.status_code, 403)

    def test_lecturer_dashboard_only_lists_permitted_students(self):
        AnalyticsEvent.objects.create(user=self.student, event_type="click", path="/learning/materials/")
        AnalyticsEvent.objects.create(user=self.outside_student, event_type="click", path="/private/")
        self.client.force_login(self.lecturer)

        response = self.client.get(reverse("analytics_app:site"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student.username)
        self.assertNotContains(response, self.outside_student.username)
        self.assertContains(response, "site-analytics-data")

    def test_tracking_endpoint_records_safe_per_user_click(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("analytics_app:track"),
            data=json.dumps(
                {
                    "event_type": "click",
                    "path": "/learning/materials/",
                    "metadata": {"label": "Open material", "element_id": "open-material"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        event = AnalyticsEvent.objects.get(event_type="click")
        self.assertEqual(event.user, self.student)
        self.assertEqual(event.metadata["label"], "Open material")

    def test_middleware_records_page_and_endpoint_events(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("core:dashboard"))

        self.assertEqual(response.status_code, 200)
        path = reverse("core:dashboard")
        self.assertTrue(AnalyticsEvent.objects.filter(user=self.student, path=path, event_type="page_view").exists())
        endpoint = AnalyticsEvent.objects.get(user=self.student, path=path, event_type="endpoint")
        self.assertEqual(endpoint.metadata["method"], "GET")
        self.assertEqual(endpoint.metadata["status_code"], 200)

    def test_material_destination_click_is_attributed_to_material(self):
        topic = Topic.objects.create(course=self.course, title="Feedback Loops")
        material = Material.objects.create(
            course=self.course,
            topic=topic,
            title="Understanding Reinforcing and Balancing Loops",
            youtube_title="Feedback Loops Explained",
            source_type=Material.SourceType.VIDEO,
            is_validated=True,
        )
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("analytics_app:track"),
            data=json.dumps(
                {
                    "event_type": "click",
                    "path": "/dashboard/",
                    "metadata": {"label": "Open material", "href_path": material.get_absolute_url()},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        event = AnalyticsEvent.objects.get(event_type="click")
        self.assertEqual(event.material, material)
        self.assertEqual(event.metadata["label"], "Video on Feedback Loops — Feedback Loops Explained")
        self.assertEqual(event.metadata["action_label"], "Open material")


class AnalyticsQuestionnaireTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="privacy-admin", email="privacy-admin@example.com", password="pass", role="admin", is_staff=True
        )
        self.student = User.objects.create_user(
            username="survey-student", email="survey-student@example.com", password="pass", role="student"
        )
        self.questionnaire = AnalyticsQuestionnaire.objects.create(
            title="Learning access survey",
            purpose="Understand broad access patterns and improve learning support.",
            is_active=True,
            reviewed_by=self.admin,
            reviewed_at=timezone.now(),
            created_by=self.admin,
        )
        AnalyticsQuestion.objects.create(
            questionnaire=self.questionnaire,
            key="gender",
            label="How do you describe your gender?",
            question_type="gender",
        )
        AnalyticsQuestion.objects.create(
            questionnaire=self.questionnaire,
            key="province",
            label="Which province do you usually access the LMS from?",
            question_type="region",
            is_required=True,
            order=2,
        )

    def test_reviewed_questionnaire_appears_until_answered(self):
        self.client.force_login(self.student)
        dashboard = self.client.get(reverse("core:dashboard"))
        self.assertContains(dashboard, 'id="analytics-questionnaire"')
        self.assertContains(dashboard, "Access Survey")
        page = self.client.get(reverse("accounts:profile"))
        self.assertContains(page, "Learning access survey")
        self.assertContains(page, "Review and participate")
        self.assertContains(page, "We do not request GPS coordinates")

        response = self.client.post(
            reverse("analytics_app:questionnaire_submit", args=[self.questionnaire.pk]),
            {"consent": "yes", "gender": "Prefer not to say", "province": "Gauteng", "browser_timezone": "Africa/Johannesburg"},
        )

        self.assertEqual(response.status_code, 200)
        stored = AnalyticsQuestionnaireResponse.objects.get(user=self.student)
        self.assertTrue(stored.consent_given)
        self.assertEqual(stored.answers["province"], "Gauteng")
        self.assertEqual(stored.answers["browser_timezone"], "Africa/Johannesburg")
        self.assertNotContains(self.client.get(reverse("accounts:profile")), 'id="analytics-questionnaire"')

    def test_login_explains_optional_survey_before_sign_in(self):
        self.client.logout()
        page = self.client.get(reverse("login"))
        self.assertContains(page, "Optional student access survey")
        self.assertContains(page, "Participation is voluntary")

    def test_questionnaire_rejects_missing_consent_and_invalid_choices(self):
        self.client.force_login(self.student)
        no_consent = self.client.post(
            reverse("analytics_app:questionnaire_submit", args=[self.questionnaire.pk]),
            {"province": "Gauteng"},
        )
        self.assertEqual(no_consent.status_code, 400)
        invalid = self.client.post(
            reverse("analytics_app:questionnaire_submit", args=[self.questionnaire.pk]),
            {"consent": "yes", "province": "Exact home address"},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(AnalyticsQuestionnaireResponse.objects.count(), 0)

    def test_user_can_withdraw_and_delete_response(self):
        response = AnalyticsQuestionnaireResponse.objects.create(
            questionnaire=self.questionnaire,
            user=self.student,
            answers={"province": "Gauteng"},
            consent_given=True,
            consented_at=timezone.now(),
            consent_version="v1",
        )
        self.client.force_login(self.student)

        result = self.client.post(
            reverse("analytics_app:questionnaire_withdraw", args=[response.pk]),
            {"next": reverse("accounts:profile")},
        )

        self.assertRedirects(result, reverse("accounts:profile"))
        self.assertFalse(AnalyticsQuestionnaireResponse.objects.filter(pk=response.pk).exists())

    def test_ethics_workspace_is_admin_only(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("analytics_app:ethics")).status_code, 403)

        self.client.force_login(self.admin)
        page = self.client.get(reverse("analytics_app:ethics"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Ethics &amp; Surveys")
        self.assertContains(page, self.questionnaire.title)
        self.assertContains(page, "Configure")
