from urllib.error import HTTPError
from unittest.mock import patch

from django.test import TestCase

from accounts.models import User
from learning.models import AssessmentQuestion, BaselineAssessment, Course, Topic
from learning.services.assessment import grade_assessment


class AssessmentServiceTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student1",
            password="password123",
            email="student1@example.com",
        )
        self.course = Course.objects.create(code="CSC101", title="Intro to Computing")
        self.topic = Topic.objects.create(course=self.course, title="Algorithms")
        self.assessment = BaselineAssessment.objects.create(course=self.course, title="Week 1 Baseline")
        self.mcq = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            topic=self.topic,
            prompt="What is 2 + 2?",
            question_type=AssessmentQuestion.QuestionType.MULTIPLE_CHOICE,
            options=["3", "4", "5"],
            correct_option="4",
            order=1,
        )
        self.short = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            topic=self.topic,
            prompt="Name one algorithm design technique.",
            question_type=AssessmentQuestion.QuestionType.SHORT_TEXT,
            expected_keywords="divide and conquer, greedy",
            order=2,
        )

    def test_grade_assessment_scores_answers(self):
        attempt = grade_assessment(
            self.assessment,
            self.student,
            {
                f"question_{self.mcq.pk}": "4",
                f"question_{self.short.pk}": "A greedy strategy can help.",
            },
        )

        self.assertEqual(float(attempt.score), 100.0)
        self.assertEqual(attempt.answers.count(), 2)

    @patch("learning.views.urllib_request.urlopen")
    def test_openalex_pdf_proxy_streams_pdf(self, mock_urlopen):
        class _MockResponse:
            headers = {"Content-Type": "application/pdf"}

            def read(self):
                return b"%PDF-test"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        mock_urlopen.return_value = _MockResponse()
        self.client.login(username="student1", password="password123")
        response = self.client.get("/learning/materials/openalex/W123/pdf/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("inline; filename=\"W123.pdf\"", response["Content-Disposition"])

    @patch("learning.views.urllib_request.urlopen")
    def test_openalex_pdf_proxy_redirects_to_fallback_on_http_error(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="https://content.openalex.org/works/W123.pdf",
            code=402,
            msg="Payment Required",
            hdrs=None,
            fp=None,
        )
        self.client.login(username="student1", password="password123")
        response = self.client.get(
            "/learning/materials/openalex/W123/pdf/?fallback=https%3A%2F%2Fdoi.org%2F10.1000%2Fexample"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://doi.org/10.1000/example")

# Create your tests here.
