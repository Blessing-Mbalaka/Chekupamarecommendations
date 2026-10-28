from django.conf import settings
from tempfile import TemporaryDirectory
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
            course=self.sys, title="Sys notes", source_type=Material.SourceType.FILE, is_validated=True
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

    def test_admin_can_create_demo_user_with_temporary_password_without_email(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("core:manage_user_new"),
            {
                "username": "demo-with-password",
                "email": "demo-with-password@example.com",
                "role": UserRole.STUDENT,
                "temporary_password": "Demo-Access-Password-472!",
                "confirm_temporary_password": "Demo-Access-Password-472!",
                "courses": [self.sys.pk],
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("core:manage_users"))
        created = User.objects.get(username="demo-with-password")
        self.assertTrue(created.check_password("Demo-Access-Password-472!"))
        self.assertEqual(len(mail.outbox), 0)

    def test_temporary_password_confirmation_must_match(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("core:manage_user_new"),
            {
                "username": "mismatched-password",
                "email": "mismatched-password@example.com",
                "role": UserRole.STUDENT,
                "temporary_password": "Demo-Access-Password-472!",
                "confirm_temporary_password": "Different-Password-629!",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "temporary passwords do not match")
        self.assertFalse(User.objects.filter(username="mismatched-password").exists())

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
