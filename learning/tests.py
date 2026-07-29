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

# Create your tests here.
