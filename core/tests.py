from django.test import TestCase
from django.urls import reverse

from accounts.models import User


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
