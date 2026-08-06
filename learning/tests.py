from urllib.error import HTTPError
from unittest.mock import patch
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from ingestion.models import ContentChunk
from learning.forms_curation import MaterialUploadForm
from learning.models import AssessmentQuestion, BaselineAssessment, Course, Material, Quiz, QuizQuestion, Topic
from learning.services.assessment import grade_assessment
from learning.services.quizzes import generate_quiz_questions, parse_quiz_json, validate_quiz_json


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
        self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")

    def test_openalex_material_gets_same_origin_pdf_preview(self):
        material = Material.objects.create(
            course=self.course,
            title="Indexed paper",
            source_type=Material.SourceType.PAPER,
            source_provider="OpenAlex",
            source_record_id="https://openalex.org/W123",
            external_url="https://doi.org/10.1000/example",
            is_validated=True,
        )

        self.assertEqual(material.preview_kind, "pdf")
        self.assertEqual(material.preview_url, "/learning/materials/openalex/W123/pdf/")

    def test_uploaded_pdf_preview_is_authenticated_and_same_origin(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            material = Material.objects.create(
                course=self.course,
                title="Uploaded journal",
                source_type=Material.SourceType.JOURNAL,
                file=SimpleUploadedFile("journal.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
                is_validated=True,
            )
            self.client.login(username="student1", password="password123")
            response = self.client.get(material.preview_url)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")
            response.close()

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

class MaterialUploadFormTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(code="UPLOAD101", title="Upload Testing")

    def test_uploaded_pdf_can_leave_optional_metadata_blank(self):
        form = MaterialUploadForm(
            data={"course": self.course.pk, "title": "Course notes", "source_type": Material.SourceType.FILE},
            files={"file": SimpleUploadedFile("notes.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf")},
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.fields["description"].required)
        self.assertFalse(form.fields["publication_year"].required)
        self.assertFalse(form.fields["doi"].required)
        self.assertFalse(form.fields["isbn"].required)

    def test_uploaded_file_type_requires_a_file(self):
        form = MaterialUploadForm(
            data={"course": self.course.pk, "title": "Missing file", "source_type": Material.SourceType.FILE}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    def test_journal_requires_attribution_and_a_source(self):
        form = MaterialUploadForm(
            data={
                "course": self.course.pk,
                "title": "Journal reading",
                "source_type": Material.SourceType.JOURNAL,
                "authors": "A. Researcher",
                "external_url": "https://example.com/paper.pdf",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("journal_name", form.errors)

    def test_website_requires_external_url(self):
        form = MaterialUploadForm(
            data={"course": self.course.pk, "title": "Reference site", "source_type": Material.SourceType.WEBSITE}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("external_url", form.errors)

    def test_uploaded_file_rejects_video_only_fields(self):
        form = MaterialUploadForm(
            data={
                "course": self.course.pk,
                "title": "Feedback loop notes",
                "source_type": Material.SourceType.FILE,
                "source_preview_url": "https://youtu.be/UiJFZKN0Ncs",
                "youtube_title": "Feedback Loop",
            },
            files={"file": SimpleUploadedFile("notes.txt", b"feedback loop transcript", content_type="text/plain")},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("source_preview_url", form.errors)
        self.assertIn("youtube_title", form.errors)


class MaterialPreviewTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(code="PREVIEW101", title="Preview Testing")

    def test_youtube_url_in_document_preview_field_is_not_treated_as_pdf(self):
        material = Material.objects.create(
            course=self.course,
            title="Feedback Loop",
            source_type=Material.SourceType.FILE,
            source_preview_url="https://youtu.be/UiJFZKN0Ncs",
            is_validated=True,
        )

        self.assertEqual(material.document_preview_url, "")
        self.assertEqual(material.preview_kind, "link")


class QuizBuilderTests(TestCase):
    def setUp(self):
        self.lecturer = User.objects.create_user(
            username="lecturer1", password="password123", email="lecturer1@example.com", role="lecturer"
        )
        self.student = User.objects.create_user(
            username="quizstudent", password="password123", email="quizstudent@example.com", role="student"
        )
        self.course = Course.objects.create(code="SYS201", title="Systems Practice")
        self.course.lecturers.add(self.lecturer)
        self.course.students.add(self.student)
        self.material = Material.objects.create(
            course=self.course, title="Feedback loops", is_validated=True, source_type=Material.SourceType.FILE
        )
        ContentChunk.objects.create(
            material=self.material,
            ordinal=0,
            text="A reinforcing feedback loop amplifies change while a balancing loop resists change.",
        )
        self.quiz = Quiz.objects.create(
            course=self.course, title="Feedback Quiz", created_by=self.lecturer, is_published=True
        )

    def test_lecturer_can_open_builder_but_student_cannot(self):
        self.client.login(username="lecturer1", password="password123")
        self.assertEqual(self.client.get(reverse("learning:quiz_builder")).status_code, 200)
        self.client.login(username="quizstudent", password="password123")
        self.assertEqual(self.client.get(reverse("learning:quiz_builder")).status_code, 403)

    def test_quiz_json_parser_rejects_prose_and_wrong_structure(self):
        valid = (
            '[{"prompt":"Explain feedback","question_type":"text","options":[],'
            f'"correct_answer":"feedback","explanation":"From source","source_material_id":{self.material.pk}}}]'
        )
        self.assertEqual(len(parse_quiz_json(f"```json\n{valid}\n```")), 1)
        self.assertEqual(parse_quiz_json(f"Here are the questions:\n{valid}"), [])
        self.assertEqual(parse_quiz_json('{"questions": []}'), [])
        malformed_schema = parse_quiz_json(
            f'[{{"prompt":"Missing fields","question_type":"text","options":[],"source_material_id":{self.material.pk}}}]'
        )
        self.assertEqual(
            validate_quiz_json(malformed_schema, allowed_material_ids={self.material.pk}, count=1),
            [],
        )

    @patch("learning.services.quizzes.generate_chat_text")
    def test_llm_json_questions_are_created_as_editable_drafts(self, mock_generate):
        mock_generate.return_value = (
            '[{"prompt":"Which loop amplifies change?","question_type":"mcq",'
            '"options":["Reinforcing","Balancing"],"correct_answer":"Reinforcing",'
            '"explanation":"The source says reinforcing loops amplify change.",'
            f'"source_material_id":{self.material.pk}}}]',
            "gemini",
        )
        created, backend = generate_quiz_questions(self.quiz, [self.material], count=1)

        self.assertEqual(backend, "gemini")
        self.assertTrue(created[0].is_ai_generated)
        self.assertEqual(created[0].options, ["Reinforcing", "Balancing"])

        self.client.login(username="lecturer1", password="password123")
        response = self.client.post(
            reverse("learning:quiz_question_edit", args=[self.quiz.pk, created[0].pk]),
            {
                "source_material": self.material.pk,
                "prompt": "Which feedback loop amplifies change?",
                "question_type": "mcq",
                "options_text": "Reinforcing\nBalancing",
                "correct_answer": "Reinforcing",
                "explanation": "Edited by lecturer.",
                "points": 2,
                "order": 1,
            },
        )
        self.assertEqual(response.status_code, 302)
        created[0].refresh_from_db()
        self.assertEqual(created[0].points, 2)
        self.assertEqual(created[0].explanation, "Edited by lecturer.")
        self.assertTrue(created[0].is_reviewed)

    @patch("learning.services.quizzes.generate_chat_text")
    def test_malformed_local_llm_json_gets_one_strict_repair_attempt(self, mock_generate):
        repaired = (
            '[{"prompt":"Which loop resists change?","question_type":"mcq",'
            '"options":["Balancing","Reinforcing"],"correct_answer":"Balancing",'
            '"explanation":"Balancing loops resist change.",'
            f'"source_material_id":{self.material.pk}}}]'
        )
        mock_generate.side_effect = [
            ("Here is your quiz: {prompt: broken}", "ollama"),
            (repaired, "ollama"),
        ]

        created, backend = generate_quiz_questions(self.quiz, [self.material], count=1)

        self.assertEqual(mock_generate.call_count, 2)
        self.assertEqual(backend, "ollama-json-repair")
        self.assertEqual(created[0].correct_answer, "Balancing")

    @patch("learning.services.quizzes.generate_chat_text")
    def test_unrepairable_model_text_is_never_saved_as_a_question(self, mock_generate):
        mock_generate.side_effect = [
            ("I could not make JSON today.", "ollama"),
            ("Still not JSON", "ollama"),
        ]

        created, backend = generate_quiz_questions(self.quiz, [self.material], count=1)

        self.assertEqual(backend, "deterministic-fallback")
        self.assertEqual(len(created), 1)
        self.assertNotIn("Still not JSON", created[0].prompt)

    def test_library_material_opens_prefilled_ai_quiz_flow(self):
        self.client.login(username="lecturer1", password="password123")
        material_page = self.client.get(reverse("learning:material_detail", args=[self.material.pk]))
        self.assertContains(material_page, "Make a quiz from this")

        builder = self.client.get(reverse("learning:quiz_builder") + f"?material={self.material.pk}")
        self.assertContains(builder, f"{self.material.title} Quiz")
        self.assertContains(builder, f'name="source_material" value="{self.material.pk}"', html=False)

        response = self.client.post(
            reverse("learning:quiz_builder") + f"?material={self.material.pk}",
            {
                "source_material": self.material.pk,
                "course": self.course.pk,
                "title": "Material Quiz",
                "description": "Generated from a library item",
                "instructions": "Answer carefully",
                "is_published": "on",
            },
        )
        created_quiz = Quiz.objects.get(title="Material Quiz")
        self.assertFalse(created_quiz.is_published)
        self.assertRedirects(
            response,
            reverse("learning:quiz_builder_detail", args=[created_quiz.pk]) + f"?mode=ai&material={self.material.pk}",
            fetch_redirect_response=False,
        )

    def test_unreviewed_ai_draft_blocks_publication(self):
        QuizQuestion.objects.create(
            quiz=self.quiz,
            prompt="AI draft",
            question_type="text",
            correct_answer="feedback",
            is_ai_generated=True,
            is_reviewed=False,
        )
        self.quiz.is_published = False
        self.quiz.save(update_fields=["is_published"])
        self.client.login(username="lecturer1", password="password123")
        response = self.client.post(
            reverse("learning:quiz_builder_detail", args=[self.quiz.pk]),
            {
                "action": "update_quiz",
                "quiz-course": self.course.pk,
                "quiz-title": self.quiz.title,
                "quiz-description": "",
                "quiz-instructions": "",
                "quiz-is_published": "on",
            },
        )
        self.quiz.refresh_from_db()
        self.assertFalse(self.quiz.is_published)
        self.assertContains(response, "Review every AI draft before publishing")
        self.assertContains(response, "AI-assisted mode")
        self.assertContains(response, "Manual mode")

    def test_student_can_take_published_quiz_and_see_result(self):
        question = QuizQuestion.objects.create(
            quiz=self.quiz,
            prompt="Which loop amplifies change?",
            question_type=QuizQuestion.QuestionType.MULTIPLE_CHOICE,
            options=["Reinforcing", "Balancing"],
            correct_answer="Reinforcing",
            points=2,
        )
        self.client.login(username="quizstudent", password="password123")
        response = self.client.post(
            reverse("learning:quiz_take", args=[self.quiz.pk]),
            {f"question_{question.pk}": "Reinforcing"},
            follow=True,
        )
        self.assertContains(response, "100.0%")
        self.assertContains(response, "Correct")
