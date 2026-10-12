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


class AccountHardeningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user('admin', 'admin@example.com', 'pwd')
        cls.admin.groups.add(Group.objects.get(name=Role.ADMIN))
        cls.student = User.objects.create_user('eleve', 'eleve@example.com', 'Ancien-Mot-2026')
        cls.student.groups.add(Group.objects.get(name=Role.STUDENT))

    def test_only_login_and_logout_allauth_pages(self):
        self.assertEqual(self.client.get(reverse('account_login')).status_code, 200)
        for path in ['/accounts/signup/', '/accounts/password/reset/', '/accounts/email/',
                     '/accounts/password/change/', '/invitations/send-invite/']:
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_accept_invite_enforces_password_validators(self):
        from .views import create_invited_user
        user = create_invited_user('nouveau@example.com', Role.STUDENT)
        url = reverse('userManagement:accept_invite', args=[user.invite_token])
        response = self.client.post(url, {'username': 'nouveau', 'password1': '1234', 'password2': '1234'})
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.client.post(url, {'username': 'nouveau', 'password1': 'Plongee-2026!', 'password2': 'Plongee-2026!'})
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_change_password_enforces_validators(self):
        self.client.force_login(self.student)
        url = reverse('userManagement:change_password')
        self.client.post(url, {'old_password': 'Ancien-Mot-2026', 'new_password1': '1234', 'new_password2': '1234'})
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password('Ancien-Mot-2026'))
        self.client.post(url, {'old_password': 'Ancien-Mot-2026',
                               'new_password1': 'Plongee-2026!', 'new_password2': 'Plongee-2026!'})
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password('Plongee-2026!'))

    def test_reset_link_back_url_ignores_external_next(self):
        self.client.force_login(self.admin)
        url = reverse('userManagement:password_reset_link', args=[self.student.pk])
        for next_url in ['javascript:alert(1)', 'https://evil.example.com/']:
            response = self.client.post(url, {'next': next_url})
            self.assertEqual(response.context['back_url'], reverse('userManagement:user_list'))
        response = self.client.post(url, {'next': '/suivi/eleves/'})
        self.assertEqual(response.context['back_url'], '/suivi/eleves/')

    def test_user_list_escapes_email_in_javascript(self):
        get_user_model().objects.create_user('piege', "x'-alert`1`-'@a.fr", 'pwd')
        self.client.force_login(self.admin)
        content = self.client.get(reverse('userManagement:user_list')).content.decode()
        self.assertNotIn("Supprimer x&#x27;", content)
        self.assertIn('Supprimer x\\u0027', content)


class InitDevDbTests(TestCase):
    @override_settings(DEBUG=False)
    def test_refuses_outside_debug(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with mock.patch('os.remove') as remove, self.assertRaises(CommandError):
            call_command('init_dev_db')
        remove.assert_not_called()


class SuperuserProtectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.root = User.objects.create_superuser('root', 'root@example.com', 'pwd')
        cls.admin = User.objects.create_user('admin', 'admin@example.com', 'pwd')
        cls.admin.groups.add(Group.objects.get(name=Role.ADMIN))

    def test_admin_cannot_take_over_or_delete_superuser(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('userManagement:password_reset_link', args=[self.root.pk])).url,
                         reverse('home'))
        self.assertEqual(self.client.get(reverse('userManagement:user_role', args=[self.root.pk])).status_code, 404)
        self.client.post(reverse('userManagement:user_delete', args=[self.root.pk]))
        self.assertTrue(get_user_model().objects.filter(pk=self.root.pk).exists())
        self.assertNotContains(self.client.get(reverse('userManagement:user_list')),
                               reverse('userManagement:user_delete', args=[self.root.pk]))

    def test_superuser_can_manage_admin(self):
        self.client.force_login(self.root)
        self.assertEqual(self.client.get(reverse('userManagement:user_role', args=[self.admin.pk])).status_code, 200)
        self.client.post(reverse('userManagement:user_delete', args=[self.admin.pk]))
        self.assertFalse(get_user_model().objects.filter(pk=self.admin.pk).exists())

    def test_invite_rejects_existing_email_whatever_the_case(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('userManagement:invite'), {'email': 'Admin@Example.com', 'role': Role.INSTRUCTOR})
        self.assertFormError(response.context['form'], 'email', 'Un utilisateur avec cet email existe déjà.')
        self.assertEqual(get_user_model().objects.filter(email__iexact='admin@example.com').count(), 1)

    def test_django_admin_login_goes_through_allauth(self):
        response = self.client.get('/admin/login/?next=/admin/')
        self.assertRedirects(response, reverse('account_login') + '?next=/admin/', fetch_redirect_response=False)
        self.client.post('/admin/login/', {'username': 'root', 'password': 'pwd'})
        self.assertNotIn('_auth_user_id', self.client.session)
        self.client.force_login(self.admin)  # connecté sans accès à l'admin : pas de boucle de redirection
        self.assertRedirects(self.client.get('/admin/login/'), reverse('home'), fetch_redirect_response=False)
        self.client.force_login(self.root)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
