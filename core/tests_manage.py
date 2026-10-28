from django.conf import settings
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import UserRole
from ingestion.models import ContentChunk
from learning.models import Course, Material

User = get_user_model()


class ManagementTests(TestCase):
    def setUp(self):
        temporary_media = TemporaryDirectory(dir=settings.BASE_DIR)
        self.addCleanup(temporary_media.cleanup)
        media_override = override_settings(MEDIA_ROOT=temporary_media.name)
        media_override.enable()
        self.addCleanup(media_override.disable)
        self.admin = User.objects.create_user("adm", "adm@x.com", "pw", role=UserRole.ADMIN)
        self.lecturer = User.objects.create_user("lec", "lec@x.com", "pw", role=UserRole.LECTURER)
        self.student = User.objects.create_user("stu", "stu@x.com", "pw", role=UserRole.STUDENT)
        self.sys = Course.objects.create(code="SYS101", title="Systems Thinking")
        self.phy = Course.objects.create(code="PHY101", title="Physics")
        self.sys.lecturers.add(self.lecturer)
        self.sys_material = Material.objects.create(
            course=self.sys,
            title="Sys notes",
            source_type=Material.SourceType.FILE,
            is_validated=True,
            uploaded_by=self.lecturer,
        )
        self.phy_material = Material.objects.create(
            course=self.phy, title="Physics notes", source_type=Material.SourceType.FILE, is_validated=True
        )
        for material in (self.sys_material, self.phy_material):
            for ordinal in range(3):
                ContentChunk.objects.create(material=material, ordinal=ordinal, text=f"chunk {ordinal}")

    def test_user_pages_are_admin_only(self):
        self.client.force_login(self.lecturer)
        self.assertEqual(self.client.get(reverse("core:manage_users")).status_code, 403)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("core:manage_users")).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("core:manage_users")).status_code, 200)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("core:manage_materials"))
        self.assertEqual(response.status_code, 302)

    def test_admin_creates_lecturer_with_courses(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("core:manage_user_new"),
            {
                "username": "newlec",
                "email": "newlec@x.com",
                "role": UserRole.LECTURER,
                "courses": [self.sys.pk, self.phy.pk],
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = User.objects.get(username="newlec")
        self.assertEqual(set(created.courses_taught.all()), {self.sys, self.phy})
        self.assertFalse(created.courses_enrolled.exists())
        self.assertFalse(created.has_usable_password())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)
        self.assertNotIn("password123", mail.outbox[0].body.lower())

    def test_admin_can_resend_setup_link_without_exposing_credentials(self):
        self.student.set_unusable_password()
        self.student.save(update_fields=["password"])
        self.client.force_login(self.admin)

        response = self.client.post(reverse("core:manage_user_invite", args=[self.student.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.student.email])
        self.assertIn("/accounts/reset/", mail.outbox[0].body)
        self.assertNotIn("EMAIL_HOST_PASSWORD", mail.outbox[0].body)

    def test_admin_creates_pending_user_without_email(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("core:manage_user_new"),
            {
                "username": "pending-lecturer",
                "email": "pending-lecturer@example.com",
                "role": UserRole.LECTURER,
                "courses": [self.sys.pk],
            },
        )
        self.assertRedirects(response, reverse("core:manage_users"))
        created = User.objects.get(username="pending-lecturer")
        self.assertFalse(created.is_active)
        self.assertFalse(created.has_usable_password())
        self.assertEqual(len(mail.outbox), 0)

    def test_activation_sends_setup_link_and_approved_modules(self):
        pending = User.objects.create_user(
            "pending", "pending@example.com", role=UserRole.LECTURER, is_active=False
        )
        pending.set_unusable_password()
        pending.save(update_fields=["password"])
        pending.courses_taught.add(self.sys)
        self.client.force_login(self.admin)
        response = self.client.post(reverse("core:manage_user_toggle", args=[pending.pk]))
        self.assertRedirects(response, reverse("core:manage_users"))
        pending.refresh_from_db()
        self.assertTrue(pending.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [pending.email])
        self.assertIn("/accounts/reset/", mail.outbox[0].body)
        self.assertIn("SYS101", mail.outbox[0].body)
        self.assertTrue(mail.outbox[0].alternatives)
        self.assertIn("Create your secure password", mail.outbox[0].alternatives[0].content)

    @patch("core.manage_views.send_account_setup_email", side_effect=RuntimeError("SMTP unavailable"))
    def test_failed_activation_email_keeps_account_pending(self, mocked_send):
        pending = User.objects.create_user(
            "pending-failure", "pending-failure@example.com", role=UserRole.LECTURER, is_active=False
        )
        self.client.force_login(self.admin)
        response = self.client.post(reverse("core:manage_user_toggle", args=[pending.pk]), follow=True)
        pending.refresh_from_db()
        self.assertFalse(pending.is_active)
        self.assertContains(response, "account remains pending")
        mocked_send.assert_called_once()

    def test_active_lecturer_is_emailed_when_module_allocation_changes(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("core:manage_user_edit", args=[self.lecturer.pk]),
            {
                "username": self.lecturer.username,
                "email": self.lecturer.email,
                "role": UserRole.LECTURER,
                "courses": [self.sys.pk, self.phy.pk],
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("core:manage_users"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("module allocation", mail.outbox[0].subject.lower())
        self.assertIn("PHY101", mail.outbox[0].body)

    def test_changing_role_moves_course_relationship(self):
        self.sys.students.add(self.student)
        self.client.force_login(self.admin)
        self.client.post(
            reverse("core:manage_user_edit", args=[self.student.pk]),
            {
                "username": "stu",
                "email": "stu@x.com",
                "role": UserRole.TA,
                "courses": [self.sys.pk],
                "is_active": "on",
            },
        )
        self.student.refresh_from_db()
        self.assertEqual(list(self.student.courses_supported.all()), [self.sys])
        self.assertFalse(self.student.courses_enrolled.exists())

    def test_lecturer_only_sees_own_course_materials(self):
        self.client.force_login(self.lecturer)
        response = self.client.get(reverse("core:manage_materials"))
        titles = [m.title for m in response.context["page"]]
        self.assertEqual(titles, ["Sys notes"])

    def test_lecturer_cannot_touch_other_course_material(self):
        self.client.force_login(self.lecturer)
        self.assertEqual(
            self.client.post(reverse("core:manage_material_delete", args=[self.phy_material.pk])).status_code, 404
        )
        self.assertEqual(
            self.client.get(reverse("core:manage_material_chunks", args=[self.phy_material.pk])).status_code, 404
        )
        self.assertEqual(
            self.client.post(
                reverse("core:manage_chunks_delete", args=[self.phy_material.pk]),
                {"chunk_ids": list(self.phy_material.content_chunks.values_list("pk", flat=True))},
            ).status_code,
            404,
        )
        self.assertEqual(self.phy_material.content_chunks.count(), 3)

    def test_lecturer_can_see_but_cannot_change_colleagues_material_in_same_course(self):
        colleague = User.objects.create_user(
            "colleague-lecturer", "colleague-lecturer@example.com", "pw", role=UserRole.LECTURER
        )
        self.sys.lecturers.add(colleague)
        colleague_material = Material.objects.create(
            course=self.sys,
            title="Colleague notes",
            source_type=Material.SourceType.FILE,
            is_validated=True,
            uploaded_by=colleague,
        )
        self.client.force_login(self.lecturer)
        response = self.client.get(reverse("core:manage_materials"))
        self.assertContains(response, "Sys notes")
        self.assertContains(response, "Colleague notes")
        self.assertContains(response, "View only")
        self.assertEqual(
            self.client.get(reverse("core:manage_material_edit", args=[colleague_material.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(reverse("core:manage_material_delete", args=[colleague_material.pk])).status_code,
            404,
        )

    def test_admin_can_oversee_all_lecturer_uploads(self):
        colleague = User.objects.create_user(
            "oversight-lecturer", "oversight-lecturer@example.com", "pw", role=UserRole.LECTURER
        )
        self.sys.lecturers.add(colleague)
        Material.objects.create(
            course=self.sys,
            title="Oversight notes",
            source_type=Material.SourceType.FILE,
            is_validated=True,
            uploaded_by=colleague,
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("core:manage_materials"), {"course": self.sys.pk})
        self.assertContains(response, "Sys notes")
        self.assertContains(response, "Oversight notes")

    def test_material_survives_lecturer_deletion_and_remains_admin_managed(self):
        departing = User.objects.create_user(
            "departing-lecturer", "departing@example.com", "pw", role=UserRole.LECTURER
        )
        self.sys.lecturers.add(departing)
        material = Material.objects.create(
            course=self.sys,
            title="Departing lecturer notes",
            source_type=Material.SourceType.FILE,
            source_provider="Uploaded by departing-lecturer",
            is_validated=True,
            uploaded_by=departing,
        )
        departing.delete()
        material.refresh_from_db()
        self.assertIsNone(material.uploaded_by)
        self.assertEqual(material.uploader_label, "departing-lecturer")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("core:manage_material_edit", args=[material.pk]))
        self.assertEqual(response.status_code, 200)

    def test_lecturer_cannot_upload_to_other_course(self):
        self.client.force_login(self.lecturer)
        response = self.client.post(
            reverse("core:manage_material_new"),
            {
                "material-course": self.phy.pk,
                "material-title": "Sneaky",
                "material-source_type": Material.SourceType.FILE,
                "material-file": SimpleUploadedFile("a.txt", b"hello world " * 20),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Material.objects.filter(title="Sneaky").exists())

    def test_lecturer_uploads_to_own_course_and_indexes(self):
        self.client.force_login(self.lecturer)
        response = self.client.post(
            reverse("core:manage_material_new"),
            {
                "material-course": self.sys.pk,
                "material-title": "Lecture 1",
                "material-source_type": Material.SourceType.FILE,
                "material-file": SimpleUploadedFile("a.txt", b"Systems thinking studies wholes. " * 30),
            },
        )
        self.assertEqual(response.status_code, 302)
        material = Material.objects.get(title="Lecture 1")
        self.assertEqual(material.course, self.sys)
        self.assertEqual(material.uploaded_by, self.lecturer)
        self.assertGreater(material.content_chunks.count(), 0)

    def test_upload_with_no_extractable_text_warns(self):
        self.client.force_login(self.lecturer)
        response = self.client.post(
            reverse("core:manage_material_new"),
            {
                "material-course": self.sys.pk,
                "material-title": "Scanned",
                "material-source_type": Material.SourceType.FILE,
                "material-file": SimpleUploadedFile("scan.png", b"\x89PNG not text"),
            },
            follow=True,
        )
        self.assertTrue(Material.objects.filter(title="Scanned").exists())
        self.assertContains(response, "no text could be extracted")

    def test_delete_selected_chunks_only_affects_that_material(self):
        self.client.force_login(self.lecturer)
        ids = list(self.sys_material.content_chunks.values_list("pk", flat=True))[:2]
        other_ids = list(self.phy_material.content_chunks.values_list("pk", flat=True))
        self.client.post(
            reverse("core:manage_chunks_delete", args=[self.sys_material.pk]),
            {"chunk_ids": ids + other_ids},
        )
        self.assertEqual(self.sys_material.content_chunks.count(), 1)
        self.assertEqual(self.phy_material.content_chunks.count(), 3)

    def test_delete_material_removes_chunks(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("core:manage_material_delete", args=[self.phy_material.pk]))
        self.assertFalse(Material.objects.filter(pk=self.phy_material.pk).exists())
        self.assertFalse(ContentChunk.objects.filter(material_id=self.phy_material.pk).exists())
