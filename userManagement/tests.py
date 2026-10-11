import importlib
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Role


class RoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user('admin', 'admin@example.com', 'pwd')
        cls.admin.groups.add(Group.objects.get(name=Role.ADMIN))
        cls.instructor = User.objects.create_user('moniteur', 'moniteur@example.com', 'pwd')
        cls.instructor.groups.add(Group.objects.get(name=Role.INSTRUCTOR))
        cls.student = User.objects.create_user('eleve', 'eleve@example.com', 'pwd')
        cls.student.groups.add(Group.objects.get(name=Role.STUDENT))

    def test_only_three_role_groups_exist(self):
        self.assertEqual(set(Group.objects.values_list('name', flat=True)), {'student', 'instructor', 'admin'})

    def test_role_flags(self):
        User = get_user_model()
        admin, instructor, student = (User.objects.get(pk=u.pk) for u in (self.admin, self.instructor, self.student))
        self.assertEqual((admin.role, admin.is_administrator, admin.is_club_staff), (Role.ADMIN, True, True))
        self.assertEqual((instructor.role, instructor.is_administrator, instructor.is_club_staff),
                         (Role.INSTRUCTOR, False, True))
        self.assertEqual((student.role, student.is_administrator, student.is_club_staff), (Role.STUDENT, False, False))
        self.assertEqual(student.role_label, 'Élève')
        superuser = User.objects.create_superuser('root', 'root@example.com', 'pwd')
        self.assertTrue(superuser.is_administrator)

    def test_access_by_role(self):
        for user, sessions_ok, users_ok in [
            (self.admin, True, True), (self.instructor, True, False), (self.student, False, False),
        ]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('suivi-sessions')).status_code == 200, sessions_ok, user)
            self.assertEqual(self.client.get(reverse('userManagement:user_list')).status_code == 200, users_ok, user)

    def test_change_role_replaces_group(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('userManagement:user_role', args=[self.student.pk]), {'role': Role.INSTRUCTOR})
        self.assertEqual(list(self.student.groups.values_list('name', flat=True)), ['instructor'])

    def test_invite_assigns_role(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('userManagement:invite'), {'email': 'new@example.com', 'role': Role.INSTRUCTOR})
        user = get_user_model().objects.get(email='new@example.com')
        self.assertFalse(user.is_active)
        self.assertEqual(user.role, Role.INSTRUCTOR)



class PasswordResetLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user('admin', 'admin@example.com', 'pwd')
        cls.admin.groups.add(Group.objects.get(name=Role.ADMIN))
        cls.instructor = User.objects.create_user('moniteur', 'moniteur@example.com', 'pwd')
        cls.instructor.groups.add(Group.objects.get(name=Role.INSTRUCTOR))
        cls.student = User.objects.create_user('eleve', 'eleve@example.com', 'old-password')
        cls.student.groups.add(Group.objects.get(name=Role.STUDENT))

    def generate_link(self, actor, target):
        self.client.force_login(actor)
        response = self.client.post(reverse('userManagement:password_reset_link', args=[target.pk]))
        self.client.logout()
        return response.context['reset_url'] if response.status_code == 200 else None

    def test_instructor_can_reset_student_only(self):
        self.assertIsNotNone(self.generate_link(self.instructor, self.student))
        self.assertIsNone(self.generate_link(self.instructor, self.admin))
        self.assertIsNone(self.generate_link(self.student, self.instructor))

    def test_reset_sets_password_and_link_is_single_use(self):
        url = self.generate_link(self.admin, self.student)
        new = {'new_password1': 'Plongee-2026!', 'new_password2': 'Plongee-2026!'}
        self.assertRedirects(self.client.post(url, new), reverse('account_login'), fetch_redirect_response=False)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password('Plongee-2026!'))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_invalid_token_is_404(self):
        url = reverse('userManagement:password_reset', args=['MQ', 'bad-token'])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_health(self):
        self.assertEqual(self.client.get(reverse('health')).content, b'ok')

    @override_settings(APP_VERSION='12 (abc1234) · publiée le 11/10/2026 14:32')
    def test_version_on_user_list(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('userManagement:user_list')),
                            'Version 12 (abc1234) · publiée le 11/10/2026 14:32')


create_initial_admin = importlib.import_module(
    'userManagement.migrations.0002_create_initial_admin').create_initial_admin


@override_settings(TESTING=False)
class InitialAdminMigrationTests(TestCase):
    def run_migration(self, **env):
        with mock.patch.dict('os.environ', env):
            create_initial_admin(django_apps, None)

    def test_creates_admin_from_env(self):
        self.run_migration(DJANGO_SUPERUSER_USERNAME='chef', DJANGO_SUPERUSER_PASSWORD='s3cret')
        user = get_user_model().objects.get(username='chef')
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password('s3cret'))
        self.assertTrue(user.groups.filter(name=Role.ADMIN).exists())

    def test_existing_admin_keeps_password(self):
        self.run_migration(DJANGO_SUPERUSER_USERNAME='chef', DJANGO_SUPERUSER_PASSWORD='s3cret')
        self.run_migration(DJANGO_SUPERUSER_USERNAME='chef', DJANGO_SUPERUSER_PASSWORD='autre')
        self.assertTrue(get_user_model().objects.get(username='chef').check_password('s3cret'))

    def test_noop_without_username_or_password(self):
        self.run_migration(DJANGO_SUPERUSER_USERNAME='', DJANGO_SUPERUSER_PASSWORD='s3cret')
        self.run_migration(DJANGO_SUPERUSER_USERNAME='chef', DJANGO_SUPERUSER_PASSWORD='')
        self.assertFalse(get_user_model().objects.exists())
