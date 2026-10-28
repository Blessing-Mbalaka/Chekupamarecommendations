from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from institutions.models import Institution
from institutions.tenancy import institution_context
from learning.models import Course

from .models import UserRole


class DeactivatedLoginTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("gone", "g@x.com", "Pw-12345-xyz", is_active=False)

    def test_deactivated_with_correct_password_gets_specific_message(self):
        response = self.client.post(reverse("login"), {"institution_code": "jbs", "username": "gone", "password": "Pw-12345-xyz"})
        self.assertContains(response, "deactivated and awaiting activation")

    def test_deactivated_with_wrong_password_stays_generic(self):
        response = self.client.post(reverse("login"), {"institution_code": "jbs", "username": "gone", "password": "nope"})
        self.assertNotContains(response, "awaiting activation")
        self.assertContains(response, "correct username and password")

    def test_active_user_logs_in(self):
        self.user.is_active = True
        self.user.save()
        response = self.client.post(reverse("login"), {"institution_code": "jbs", "username": "gone", "password": "Pw-12345-xyz"})
        self.assertEqual(response.status_code, 302)


class EffectiveRoleDisplayTests(TestCase):
    def test_superuser_is_displayed_as_platform_administrator(self):
        user = get_user_model()(username="platform-admin", role=UserRole.STUDENT, is_staff=True, is_superuser=True)
        self.assertEqual(user.effective_role_display, "Platform Administrator")

    def test_student_role_is_preserved_for_regular_user(self):
        user = get_user_model()(username="regular-student", role=UserRole.STUDENT)
        self.assertEqual(user.effective_role_display, "Student")


class PasswordResetWorkflowTests(TestCase):
    def setUp(self):
        self.other = Institution.objects.create(name="Password Reset Faculty", slug="password-reset-faculty")
        with institution_context(self.other):
            self.user = get_user_model().objects.create_user(
                "reset-user", "reset-user@example.com", "Original-Pass-723!", role=UserRole.LECTURER
            )

    def test_login_links_to_password_reset_page(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, reverse("password_reset"))
        self.assertContains(response, "Forgot your password?")

    def test_reset_email_works_across_institutions_and_contains_html(self):
        response = self.client.post(reverse("password_reset"), {"email": self.user.email})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn("/accounts/reset/", mail.outbox[0].body)
        self.assertTrue(mail.outbox[0].alternatives)
        self.assertIn("Choose a new password", mail.outbox[0].alternatives[0].content)

    def test_unknown_email_gets_same_confirmation_without_email(self):
        response = self.client.post(reverse("password_reset"), {"email": "unknown@example.com"})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_account_does_not_receive_reset(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(reverse("password_reset"), {"email": self.user.email})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)


class ModuleSettingsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            "student-modules",
            "student-modules@example.com",
            "Pw-12345-xyz",
            role=UserRole.STUDENT,
        )
        self.module_one = Course.all_institutions.create(
            institution_id=self.user.institution_id,
            code="MOD101",
            title="Module One",
        )
        self.module_two = Course.all_institutions.create(
            institution_id=self.user.institution_id,
            code="MOD102",
            title="Module Two",
        )

    def test_unassigned_student_is_guided_to_module_settings_after_login(self):
        response = self.client.post(
            reverse("login"),
            {
                "institution_code": self.user.institution.slug,
                "username": self.user.username,
                "password": "Pw-12345-xyz",
            },
        )
        self.assertRedirects(response, reverse("accounts:module_settings") + "?welcome=1")

    def test_student_can_select_multiple_modules(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("accounts:module_settings"),
            {"modules": [self.module_one.pk, self.module_two.pk]},
        )
        self.assertRedirects(response, reverse("core:dashboard"))
        self.assertEqual(
            set(self.user.courses_enrolled.values_list("pk", flat=True)),
            {self.module_one.pk, self.module_two.pk},
        )

    def test_student_cannot_select_module_from_another_institution(self):
        other = Institution.objects.create(name="Other Institution", slug="other-institution")
        other_module = Course.all_institutions.create(
            institution=other,
            code="OTHER101",
            title="Other Module",
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("accounts:module_settings"),
            {"modules": [other_module.pk]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertFalse(self.user.courses_enrolled.exists())

    def test_settings_explains_when_no_modules_exist(self):
        Course.all_institutions.filter(institution_id=self.user.institution_id).delete()
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:module_settings"))
        self.assertContains(response, "has not added any modules yet")
        self.assertContains(response, "lecturer or institution administrator")
