from django.test import TestCase
from django.urls import reverse

from accounts.models import StudentProfile, User
from learning.models import Course, Material


class ChatbotFlowTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student3",
            password="password123",
            email="student3@example.com",
        )
        StudentProfile.objects.create(user=self.student, challenges="I need simpler examples.")
        self.course = Course.objects.create(code="PHY101", title="Physics")
        Material.objects.create(
            course=self.course,
            title="Newtonian Mechanics Video",
            description="Gentle explanation with worked examples.",
            source_origin=Material.SourceOrigin.EXTERNAL,
            source_type=Material.SourceType.VIDEO,
            source_provider="YouTube",
            external_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            is_validated=True,
        )

    def test_chat_page_generates_bot_reply(self):
        self.client.login(username="student3", password="password123")
        response = self.client.post(reverse("chatbot:chat"), {"message": "Can you suggest an easy video?"}, follow=True)

        self.assertContains(response, "Recommended now")
        self.assertContains(response, "Newtonian Mechanics Video")

# Create your tests here.
