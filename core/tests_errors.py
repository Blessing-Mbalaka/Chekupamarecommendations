from django.test import TestCase, override_settings


@override_settings(DEBUG=False)
class ErrorPageTests(TestCase):
    def test_custom_404(self):
        response = self.client.get("/definitely-not-a-page/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)

    def test_csrf_failure_on_login_redirects_back(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        response = client.post("/login/", {"username": "x", "password": "y"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/login/")

    def test_csrf_failure_elsewhere_renders_page(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        response = client.post("/logout/")
        self.assertContains(response, "Session expired", status_code=403)
