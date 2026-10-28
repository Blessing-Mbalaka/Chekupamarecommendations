import tempfile
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.db import transaction
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from accounts.models import User
from core.forms_manage import ManagedUserForm
from learning.models import Course, Material, Topic, BaselineAssessment, AssessmentAttempt, Quiz, QuizAttempt
from ingestion.models import ContentChunk
from ingestion.services.vector_store import _load_scoring_corpus, _corpus_cache_key
from recommendations.services.engine import recommend_for_student
from analytics_app.models import AnalyticsEvent
from .models import Institution, Department
from .tenancy import institution_context

PASSWORD = 'Test-Complex-password-723!'

@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class InstitutionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Institution.objects.get(pk=1)
        cls.b = Institution.objects.create(name='Other university', slug='other')
        with institution_context(cls.a):
            cls.da = Department.objects.create(name='Science', code='sci')
            cls.admin = User.objects.create_user(username='institution-admin', email='admin@example.org', password=PASSWORD, role='admin')
            cls.student = User.objects.create_user(username='student', email='student@example.org', password=PASSWORD)
            cls.colleague = User.objects.create_user(username='colleague', email='colleague@example.org', password=PASSWORD)
            cls.lecturer = User.objects.create_user(username='lecturer', email='lecturer@example.org', password=PASSWORD, role='lecturer')
            cls.module = Course.objects.create(code='SCI101', title='Our module', department=cls.da)
            cls.unassigned = Course.objects.create(code='SCI102', title='Unassigned module', department=cls.da)
            cls.module.students.add(cls.student, cls.colleague)
            cls.module.lecturers.add(cls.lecturer)
            cls.material = Material.objects.create(course=cls.module, title='Our material', is_validated=True)
            cls.hidden = Material.objects.create(course=cls.unassigned, title='Unassigned material', is_validated=True)
            ContentChunk.objects.create(material=cls.material, ordinal=0, text='Our institution physics')
            ContentChunk.objects.create(material=cls.hidden, ordinal=0, text='Unassigned physics')
            cls.assessment = BaselineAssessment.objects.create(course=cls.module, title='Baseline')
            cls.quiz = Quiz.objects.create(course=cls.module, title='Quiz', is_published=True)
            cls.attempt = QuizAttempt.objects.create(quiz=cls.quiz, student=cls.colleague)
        with institution_context(cls.b):
            cls.db = Department.objects.create(name='Other science', code='sci')
            cls.other = User.objects.create_user(username='other', email='other@example.org', password=PASSWORD, role='admin')
            cls.other_module = Course.objects.create(code='SCI101', title='Other module', department=cls.db)
            cls.other_material = Material.objects.create(course=cls.other_module, title='Other material', is_validated=True)
            ContentChunk.objects.create(material=cls.other_material, ordinal=0, text='Other institution physics')

    def test_institution_registration_creates_admin_without_platform_privileges(self):
        response = self.client.post(reverse('institutions:register'), {'institution_name': 'New University', 'institution_code': 'new-university', 'username': 'new-owner', 'email': 'owner@new.org', 'password1': PASSWORD, 'password2': PASSWORD, 'role': 'admin', 'is_staff': 'on', 'is_superuser': 'on'})
        self.assertEqual(response.status_code, 302)
        user = User._base_manager.get(username='new-owner')
        self.assertEqual(user.institution.slug, 'new-university')
        self.assertEqual(user.role, 'admin')
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertNotEqual(user.institution_id, self.a.pk)

    def test_student_signup_cannot_choose_staff_role_or_another_institution(self):
        response = self.client.post(reverse('institutions:join'), {'invitation_code': self.b.join_code, 'username': 'joined', 'email': 'joined@new.org', 'password1': PASSWORD, 'password2': PASSWORD, 'role': 'admin', 'institution': self.a.pk})
        self.assertEqual(response.status_code, 302)
        user = User._base_manager.get(username='joined')
        self.assertEqual(user.institution_id, self.b.pk)
        self.assertEqual(user.role, 'student')
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertFalse(user.courses_enrolled.exists())

    def test_invalid_invite_and_weak_password_rejected(self):
        self.client.post(reverse('institutions:join'), {'invitation_code': 'wrong', 'username': 'bad', 'email': 'bad@new.org', 'password1': '123', 'password2': '123'})
        self.assertFalse(User._base_manager.filter(username='bad').exists())

    def test_login_requires_matching_institution(self):
        response = self.client.post(reverse('login'), {'institution_code': 'other', 'username': 'student', 'password': PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        response = self.client.post(reverse('login'), {'institution_code': 'jbs', 'username': 'student', 'password': PASSWORD})
        self.assertEqual(response.status_code, 302)

    def test_inactive_institution_denied(self):
        self.client.force_login(self.student)
        self.a.is_active = False
        self.a.save()
        self.assertEqual(self.client.get(reverse('core:dashboard')).status_code, 403)

    def test_student_only_sees_enrolled_modules_and_materials(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('learning:material_list'))
        self.assertContains(response, 'Our material')
        self.assertNotContains(response, 'Other material')
        self.assertNotContains(response, 'Unassigned material')
        for material in [self.hidden, self.other_material]:
            self.assertEqual(self.client.get(material.get_absolute_url()).status_code, 404)
        with institution_context(self.a, self.student):
            self.assertEqual(list(Course.objects.values_list('pk', flat=True)), [self.module.pk])
            self.assertEqual(ContentChunk.objects.count(), 1)

    def test_admin_user_management_cannot_see_other_institutions(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('core:manage_users'))
        self.assertContains(response, 'student@example.org')
        self.assertNotContains(response, 'other@example.org')
        self.assertEqual(self.client.get(reverse('core:manage_user_edit', args=[self.other.pk])).status_code, 404)

    def test_student_cannot_manage_structure(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('institutions:structure')).status_code, 403)
        self.assertEqual(self.client.get(reverse('institutions:course_management')).status_code, 403)

    def test_admin_can_manage_institution_login_code(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('institutions:course_management'), {
            'action': 'institution',
            'institution-name': 'Johannesburg Business School',
            'institution-slug': 'jbs-faculty',
            'institution-email': 'admin@jbs.example',
        })
        self.assertRedirects(response, reverse('institutions:course_management'))
        self.a.refresh_from_db()
        self.assertEqual(self.a.slug, 'jbs-faculty')
        self.assertEqual(self.a.email, 'admin@jbs.example')

    def test_lecturer_manages_topics_only_for_assigned_modules(self):
        self.client.force_login(self.lecturer)
        response = self.client.get(reverse('institutions:course_management'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Topic management')
        self.assertContains(response, self.module.code)
        self.assertNotContains(response, self.unassigned.code)

        response = self.client.post(reverse('institutions:course_management'), {
            'action': 'topic',
            'topic-course': self.module.pk,
            'topic-title': 'Lecturer topic',
            'topic-description': 'Created by the assigned lecturer.',
        })
        self.assertRedirects(response, reverse('institutions:course_management'))
        self.assertTrue(Topic._base_manager.filter(course=self.module, title='Lecturer topic').exists())

        response = self.client.post(reverse('institutions:course_management'), {
            'action': 'topic',
            'topic-course': self.unassigned.pk,
            'topic-title': 'Forbidden topic',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Topic._base_manager.filter(course=self.unassigned, title='Forbidden topic').exists())

    def test_lecturer_cannot_change_admin_course_structure(self):
        self.client.force_login(self.lecturer)
        response = self.client.post(reverse('institutions:course_management'), {
            'action': 'module',
            'module-department': self.da.pk,
            'module-code': 'FORBIDDEN',
            'module-title': 'Forbidden module',
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Course._base_manager.filter(code='FORBIDDEN').exists())

    def test_structure_creates_scoped_department_module_topic(self):
        self.client.force_login(self.other)
        self.client.post(reverse('institutions:structure'), {'action': 'department', 'department-code': 'eng', 'department-name': 'Engineering', 'institution': self.a.pk})
        department = Department._base_manager.get(code='eng')
        self.assertEqual(department.institution_id, self.b.pk)
        response = self.client.post(reverse('institutions:structure'), {'action': 'module', 'module-department': department.pk, 'module-code': 'ENG101', 'module-title': 'Engineering 101'})
        self.assertEqual(response.status_code, 302)
        module = Course._base_manager.get(code='ENG101')
        self.assertEqual(module.institution_id, self.b.pk)
        self.client.post(reverse('institutions:structure'), {'action': 'topic', 'topic-course': module.pk, 'topic-title': 'Introduction'})
        self.assertTrue(Topic._base_manager.filter(course=module, institution=self.b).exists())

    def test_cross_institution_forms_and_writes_rejected(self):
        with institution_context(self.a, self.admin):
            with self.assertRaises(ValidationError):
                Course.objects.create(code='BAD', title='Invalid', department=self.db)
            with self.assertRaises(ValidationError), transaction.atomic():
                self.module.students.add(self.other)
            with self.assertRaises(ValidationError):
                Material.objects.create(course=self.other_module, title='Invalid')
            with self.assertRaises(ValidationError):
                Material.objects.filter(pk=self.material.pk).update(course=self.other_module)
            form = ManagedUserForm()
            self.assertNotIn(self.other_module, form.fields['courses'].queryset)
            self.assertNotIn(self.db, form.fields['department'].queryset)

    def test_personal_results_remain_private_to_students(self):
        self.client.force_login(self.student)
        self.assertIn(self.client.get(reverse('learning:quiz_result', args=[self.attempt.pk])).status_code, [403, 404])
        with institution_context(self.a, self.student):
            attempt = AssessmentAttempt.objects.create(assessment=self.assessment, student=self.student, score=75)
        self.client.logout()
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse('core:dashboard')), '75')
        self.assertTrue(AssessmentAttempt._base_manager.filter(pk=attempt.pk, student=self.student, score=75).exists())

    def test_recommendations_only_use_students_modules_even_outside_request(self):
        with patch('recommendations.services.engine.embed_text', return_value=([], 'test')):
            result = recommend_for_student(self.student, use_semantic=False, generate_missing_embeddings=False)
        self.assertTrue(result)
        self.assertNotIn(self.other_material, result)
        self.assertNotIn(self.hidden, result)

    def test_retrieval_and_cache_keys_are_isolated(self):
        with institution_context(self.a, self.student):
            first = _corpus_cache_key(None)
            corpus = _load_scoring_corpus(None)
            self.assertNotIn('Other institution', str(corpus))
            self.assertNotIn('Unassigned physics', str(corpus))
        with institution_context(self.b, self.other):
            self.assertNotEqual(first, _corpus_cache_key(None))
            self.assertNotIn('Our institution', str(_load_scoring_corpus(None)))

    def test_direct_files_require_authentication_and_module_access(self):
        with tempfile.TemporaryDirectory(dir='.') as folder, override_settings(MEDIA_ROOT=folder):
            with institution_context(self.b):
                self.other_material.file.save('private.txt', SimpleUploadedFile('private.txt', b'other-private'))
            url = '/media/' + self.other_material.file.name
            self.assertEqual(self.client.get(url).status_code, 302)
            self.client.force_login(self.student)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.client.force_login(self.other)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), b'other-private')

    def test_invitation_rotation_and_analytics_isolation(self):
        old = self.a.join_code
        self.client.force_login(self.admin)
        self.client.post(reverse('institutions:structure'), {'action': 'rotate_invite'})
        self.a.refresh_from_db()
        self.assertNotEqual(old, self.a.join_code)
        with institution_context(self.b):
            AnalyticsEvent.objects.create(user=self.other, event_type='click', path='/other-private/')
        response = self.client.get(reverse('analytics_app:site'))
        self.assertNotContains(response, '/other-private/')

    def test_cached_queryset_cannot_leak_between_actors(self):
        with institution_context(self.a, self.admin):
            queryset = Material.objects.all()
            self.assertEqual(len(queryset), 2)
        with institution_context(self.a, self.student):
            self.assertEqual(list(queryset.values_list('pk', flat=True)), [self.material.pk])
            self.assertEqual([obj.pk for obj in queryset], [self.material.pk])

    def test_removing_enrolment_revokes_material_access(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.material.get_absolute_url()).status_code, 200)
        self.module.students.remove(self.student)
        self.assertEqual(self.client.get(self.material.get_absolute_url()).status_code, 404)
        self.assertEqual(recommend_for_student(self.student, use_semantic=False), [])

    def test_foreign_structure_edits_and_duplicate_codes_are_rejected(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('institutions:structure'), {'edit': 'module', 'id': self.other_module.pk}).status_code, 404)
        response = self.client.post(reverse('institutions:structure'), {'action': 'module', 'module-department': self.da.pk, 'module-code': self.module.code, 'module-title': 'Duplicate'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already in use')
        response = self.client.post(reverse('institutions:structure'), {'action': 'module', 'module-department': self.db.pk, 'module-code': 'BAD', 'module-title': 'Invalid'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Course._base_manager.filter(code='BAD').exists())

    def test_student_chat_history_is_personal(self):
        from chatbot.models import ChatSession, ChatMessage
        with institution_context(self.a):
            session = ChatSession.objects.create(student=self.colleague, course=self.module)
            ChatMessage.objects.create(session=session, sender='student', content='Colleague private conversation')
        self.client.force_login(self.student)
        response = self.client.get(reverse('chatbot:chat'), {'course': self.module.pk})
        self.assertNotContains(response, 'Colleague private conversation')

    def test_anonymous_registration_does_not_expose_invitation_codes(self):
        response = self.client.get(reverse('institutions:register'))
        self.assertNotContains(response, self.a.join_code)
        self.assertNotContains(response, self.b.join_code)

    def test_maintenance_commands_default_to_original_and_accept_explicit_institution(self):
        from io import StringIO
        from django.core.management import call_command
        self.material.semantic_text = 'Original source'
        self.material.save()
        self.other_material.semantic_text = 'Other source'
        self.other_material.save()
        original_output = StringIO()
        call_command('reindex_rag', '--dry-run', stdout=original_output)
        self.assertIn('Our material', original_output.getvalue())
        self.assertNotIn('Other material', original_output.getvalue())
        other_output = StringIO()
        call_command('institution_command', 'other', 'reindex_rag', '--dry-run', stdout=other_output)
        self.assertIn('Other material', other_output.getvalue())
        self.assertNotIn('Our material', other_output.getvalue())
