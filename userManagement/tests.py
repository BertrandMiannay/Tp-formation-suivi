from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
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
