from django.test import TestCase

from accounts.models import StudentProfile, User
from learning.models import Course, Material, Topic
from recommendations.services.engine import recommend_for_student


class RecommendationEngineTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student2",
            password="password123",
            email="student2@example.com",
        )
        StudentProfile.objects.create(
            user=self.student,
            challenges="I struggle with calculus limits and derivatives.",
        )
        self.course = Course.objects.create(code="MTH101", title="Calculus")
        topic = Topic.objects.create(course=self.course, title="Limits")
        self.matching = Material.objects.create(
            course=self.course,
            topic=topic,
            title="Limits Revision Guide",
            description="A guide to limits and derivatives.",
            source_origin=Material.SourceOrigin.INTERNAL,
            source_type=Material.SourceType.FILE,
            is_validated=True,
        )
        self.other = Material.objects.create(
            course=self.course,
            title="Chemistry Notes",
            description="Acids, bases, and salts.",
            source_origin=Material.SourceOrigin.EXTERNAL,
            source_type=Material.SourceType.PAPER,
            is_validated=True,
        )

    def test_recommendation_prefers_matching_material(self):
        recommendations = recommend_for_student(
            self.student,
            course=self.course,
            query_text="I need help understanding limits.",
            limit=2,
        )

        self.assertEqual(recommendations[0], self.matching)

# Create your tests here.
