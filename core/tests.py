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

# Create your tests here.
