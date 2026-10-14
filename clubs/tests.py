from datetime import date

from django.test import TestCase

from formation.models import Cursus, Formation, Member, Season
from suivi.models import TrainingSession

from .models import Club


class DefaultClubTestCase(TestCase):
    def test_default_club_created_by_migration(self):
        self.assertEqual(Club.objects.count(), 1)

    def test_new_objects_attached_to_default_club(self):
        club = Club.objects.get()
        cursus = Cursus.objects.create(name='N1', date=date(2026, 1, 1))
        objects = [
            cursus,
            Formation.objects.create(name='N1 2026', cursus=cursus),
            Season.objects.create(label='2025-2026'),
            Member.objects.create(first_name='Léa', last_name='Martin'),
            TrainingSession.objects.create(date=date(2026, 1, 8)),
        ]
        for obj in objects:
            self.assertEqual(obj.club, club)

    def test_default_club_recreated_if_missing(self):
        Club.objects.all().delete()
        member = Member.objects.create(first_name='Léa', last_name='Martin')
        self.assertEqual(Club.objects.get(), member.club)

    def test_deleting_club_deletes_its_data(self):
        club = Club.objects.get()
        cursus = Cursus.objects.create(name='N1', date=date(2026, 1, 1))
        Formation.objects.create(name='N1 2026', cursus=cursus)
        TrainingSession.objects.create(date=date(2026, 1, 8))
        club.delete()
        self.assertFalse(Cursus.objects.exists())
        self.assertFalse(Formation.objects.exists())
        self.assertFalse(TrainingSession.objects.exists())


class ClubIsolationTestCase(TestCase):
    """Un club ne voit ni ne modifie jamais les données d'un autre club."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        from .testing import add_role

        from formation.models import CursusCategory, Enrollment, Skill, SkillEvaluation
        from suivi.models import Attendance, Comment

        cls.admin = get_user_model().objects.create_user('admin', 'admin@example.com', 'pwd')
        add_role(cls.admin, 'admin')

        cls.home = Club.objects.get()
        cls.home_cursus = Cursus.objects.create(club=cls.home, name='Niveau 1', date=date(2026, 1, 1))
        cls.home_formation = Formation.objects.create(club=cls.home, name='N1 maison', cursus=cls.home_cursus)
        cls.home_member = Member.objects.create(club=cls.home, first_name='Alice', last_name='Maison')
        cls.home_session = TrainingSession.objects.create(club=cls.home, date=date(2026, 10, 7))

        cls.other = Club.objects.create(name='Autre club')
        cls.season = Season.objects.create(club=cls.other, label='Saison autre', current=True)
        cls.cursus = Cursus.objects.create(club=cls.other, name='Cursus autre', date=date(2026, 1, 1))
        cls.skill = Skill.objects.create(
            category=CursusCategory.objects.create(cursus=cls.cursus, name='Technique'), name='Compétence autre',
        )
        cls.formation = Formation.objects.create(club=cls.other, name='Formation autre', cursus=cls.cursus)
        cls.member = Member.objects.create(club=cls.other, first_name='Zoé', last_name='Ailleurs')
        Enrollment.objects.create(member=cls.member, formation=cls.formation)
        cls.session = TrainingSession.objects.create(
            club=cls.other, season=cls.season, date=date(2026, 10, 8), title='Séance autre',
        )
        cls.session.formations.add(cls.formation)
        Attendance.objects.create(session=cls.session, member=cls.member, status=Attendance.Status.PRESENT)
        cls.comment = Comment.objects.create(member=cls.member, session=cls.session, date=date(2026, 10, 8),
                                             content='Commentaire autre')
        cls.evaluation = SkillEvaluation.objects.create(member=cls.member, skill=cls.skill, date=date(2026, 10, 8),
                                                        status='acquired')

    def setUp(self):
        self.client.force_login(self.admin)

    def _use_club(self, club):
        session = self.client.session
        session['club_id'] = club.pk
        session.save()

    def test_detail_pages_of_another_club_are_not_found(self):
        from django.urls import reverse
        urls = [
            reverse('suivi-session-detail', args=[self.session.pk]),
            reverse('suivi-student-detail', args=[self.member.pk]),
            reverse('eleve-edit', args=[self.member.pk]),
            reverse('eleve-evaluation', args=[self.member.pk]),
            reverse('eleve-evaluation-export', args=[self.member.pk, self.cursus.pk]),
            reverse('formation-detail', args=[self.formation.pk]),
            reverse('formation-fiche-vierge', args=[self.formation.pk]),
            reverse('saison-cursus-detail', args=[self.cursus.pk]),
            reverse('saison-cursus-export', args=[self.cursus.pk]),
            reverse('saison-cursus-fiche-vierge', args=[self.cursus.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_actions_on_another_club_are_refused(self):
        from django.urls import reverse
        from formation.models import SkillEvaluation
        from suivi.models import Comment
        posts = [
            (reverse('eleve-delete', args=[self.member.pk]), {}),
            (reverse('eleve-evaluation-save', args=[self.member.pk, self.cursus.pk]),
             {f'skill_{self.skill.pk}_status': 'not_acquired'}),
            (reverse('eleve-evaluation-delete', args=[self.member.pk, self.evaluation.pk]), {}),
            (reverse('saison-set-current', args=[self.season.pk]), {}),
            (reverse('saison-cursus-archiver', args=[self.cursus.pk]), {}),
            (reverse('saison-cursus-supprimer', args=[self.cursus.pk]), {}),
            (reverse('suivi-session-delete', args=[self.session.pk]), {}),
            (reverse('suivi-comment', args=[self.comment.pk]), {'comment_action': 'delete'}),
            (reverse('suivi-session-detail', args=[self.session.pk]), {'_action': 'attendance'}),
            (reverse('formation-detail', args=[self.formation.pk]), {'_action': 'toggle_status'}),
        ]
        for url, data in posts:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, data).status_code, 404)
        # Suppression de saison : sans effet hors du club.
        self.client.post(reverse('saison-delete', args=[self.season.pk]))
        self.assertTrue(Season.objects.filter(pk=self.season.pk, current=True).exists())
        self.assertTrue(Member.objects.filter(pk=self.member.pk).exists())
        self.assertTrue(Comment.objects.filter(pk=self.comment.pk).exists())
        self.assertTrue(SkillEvaluation.objects.filter(pk=self.evaluation.pk).exists())
        self.assertEqual(Cursus.objects.get(pk=self.cursus.pk).status, Cursus.Status.ACTIVE)
        self.assertEqual(Formation.objects.get(pk=self.formation.pk).status, Formation.Status.ACTIVE)

    def test_cannot_link_own_objects_to_another_club(self):
        from django.urls import reverse
        from formation.models import Enrollment
        from suivi.models import Attendance
        resp = self.client.post(reverse('formation-detail', args=[self.home_formation.pk]),
                                {'_action': 'enroll', 'member_id': self.member.pk})
        self.assertEqual(resp.status_code, 404)
        resp = self.client.post(reverse('suivi-student-detail', args=[self.home_member.pk]),
                                {'_action': 'enroll', 'formation_id': self.formation.pk})
        self.assertEqual(resp.status_code, 404)
        for action in ('add_member', 'worked_skills'):
            resp = self.client.post(reverse('suivi-session-detail', args=[self.home_session.pk]),
                                    {'_action': action, 'member_id': self.member.pk})
            self.assertEqual(resp.status_code, 404)
        self.assertFalse(Enrollment.objects.filter(member=self.home_member, formation=self.formation).exists())
        self.assertFalse(Attendance.objects.filter(session=self.home_session).exists())

        # Formation d'un autre club proposée à une séance, cursus d'un autre club à une formation : refusés.
        resp = self.client.post(reverse('suivi-session-create'), {
            'date': '2026-10-09', 'formations': [self.formation.pk], 'instructors': [], 'notes': '',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(TrainingSession.objects.filter(date=date(2026, 10, 9)).exists())
        resp = self.client.post(reverse('formation-create'), {'name': 'Intruse', 'cursus': self.cursus.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Formation.objects.filter(name='Intruse').exists())
        resp = self.client.post(reverse('eleve-create'), {
            'first_name': 'Paul', 'last_name': 'Neuf', 'formation': self.formation.pk,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Member.objects.filter(first_name='Paul').exists())

    def test_lists_only_show_the_active_club(self):
        from django.urls import reverse
        pages = [
            (reverse('suivi-sessions') + f'?season={self.season.pk}', 'Séance autre'),
            (reverse('suivi-students') + '?formation=all', 'Ailleurs'),
            (reverse('suivi-students') + '?vue=presences', 'Ailleurs'),
            (reverse('formation-list'), 'Formation autre'),
            (reverse('saison-gestion'), 'Saison autre'),
            (reverse('saison-cursus'), 'Cursus autre'),
            (reverse('eleve-create'), 'Formation autre'),
            (reverse('eleve-import'), 'Formation autre'),
            (reverse('suivi-session-create'), 'Formation autre'),
            (reverse('formation-create'), 'Cursus autre'),
            (reverse('formation-detail', args=[self.home_formation.pk]), 'Ailleurs'),
            (reverse('suivi-session-detail', args=[self.home_session.pk]), 'Ailleurs'),
            (reverse('suivi-student-detail', args=[self.home_member.pk]), 'Formation autre'),
        ]
        for url, foreign_text in pages:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                self.assertNotContains(resp, foreign_text)

    def test_active_club_from_session(self):
        from django.urls import reverse
        from .testing import add_role
        add_role(self.admin, 'admin', self.other)
        self._use_club(self.other)
        self.assertContains(self.client.get(reverse('formation-list')), 'Formation autre')
        self.assertNotContains(self.client.get(reverse('formation-list')), 'N1 maison')

        self.client.post(reverse('saison-gestion'), {'label': 'Nouvelle saison'})
        self.client.post(reverse('saison-cursus-creer'), {'name': 'Nouveau cursus', 'date': '2026-01-01'})
        self.client.post(reverse('eleve-create'), {'first_name': 'Paul', 'last_name': 'Neuf'})
        self.client.post(reverse('suivi-session-create'), {
            'date': '2026-10-09', 'formations': [self.formation.pk], 'instructors': [], 'notes': '',
        })
        self.client.post(reverse('formation-create'), {'name': 'Nouvelle formation', 'cursus': self.cursus.pk})
        self.assertEqual(Season.objects.get(label='Nouvelle saison').club, self.other)
        self.assertEqual(Cursus.objects.get(name='Nouveau cursus').club, self.other)
        self.assertEqual(Member.objects.get(first_name='Paul').club, self.other)
        session = TrainingSession.objects.get(date=date(2026, 10, 9))
        self.assertEqual((session.club, session.season), (self.other, self.season))
        self.assertEqual(Formation.objects.get(name='Nouvelle formation').club, self.other)

    def test_unknown_club_in_session_falls_back_to_default(self):
        from django.urls import reverse
        session = self.client.session
        session['club_id'] = 999999
        session.save()
        self.assertContains(self.client.get(reverse('formation-list')), 'N1 maison')


class MultiClubRolesTestCase(TestCase):
    """Un compte, plusieurs clubs : rôle propre à chaque club, club actif choisi parmi les siens,
    comptes partagés jamais exposés d'un club à l'autre."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        from .models import Membership
        User = get_user_model()
        cls.club_a = Club.objects.get()
        cls.club_a.name = 'Alpha plongée'
        cls.club_a.save()
        cls.club_b = Club.objects.create(name='Club B')
        # Paul : administrateur du club A, élève du club B.
        cls.paul = User.objects.create_user('paul', 'paul@example.com', 'pwd')
        Membership.objects.create(user=cls.paul, club=cls.club_a, role='admin')
        Membership.objects.create(user=cls.paul, club=cls.club_b, role='student')
        cls.paul_fiche_b = Member.objects.create(club=cls.club_b, user=cls.paul, first_name='Paul', last_name='Double')
        cls.admin_b = User.objects.create_user('admin_b', 'admin_b@example.com', 'pwd')
        Membership.objects.create(user=cls.admin_b, club=cls.club_b, role='admin')
        cls.instructor_a = User.objects.create_user('moniteur_a', 'moniteur_a@example.com', 'pwd')
        Membership.objects.create(user=cls.instructor_a, club=cls.club_a, role='instructor')
        cls.instructor_b = User.objects.create_user('moniteur_b', 'moniteur_b@example.com', 'pwd')
        Membership.objects.create(user=cls.instructor_b, club=cls.club_b, role='instructor')

    def _choose(self, club):
        from django.urls import reverse
        return self.client.post(reverse('club-choose'), {'club_id': club.pk})

    def test_role_depends_on_active_club(self):
        from django.urls import reverse
        self.client.force_login(self.paul)
        self._choose(self.club_a)
        self.assertEqual(self.client.get(reverse('userManagement:user_list')).status_code, 200)
        self._choose(self.club_b)
        self.assertEqual(self.client.get(reverse('userManagement:user_list')).status_code, 403)
        self.assertRedirects(self.client.get(reverse('suivi-sessions')), reverse('home'))
        response = self.client.get(reverse('suivi-mine'))
        self.assertEqual([s['member'] for s in response.context['sheets']], [self.paul_fiche_b])
        home = self.client.get(reverse('home'))
        self.assertContains(home, 'Mon suivi')
        self.assertContains(home, 'Club B')

    def test_first_login_with_several_clubs_asks_for_a_club_then_remembers_it(self):
        from django.urls import reverse
        self.client.force_login(self.paul)
        self.assertRedirects(self.client.get(reverse('home')), reverse('club-choose'))
        response = self.client.get(reverse('club-choose'))
        self.assertContains(response, 'Club B')
        self.assertContains(response, 'Administrateur')
        self._choose(self.club_b)
        self.paul.refresh_from_db()
        self.assertEqual(self.paul.last_club, self.club_b)
        # Nouvelle connexion : le dernier club utilisé est rouvert.
        self.client.logout()
        self.client.force_login(self.paul)
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.wsgi_request.club, self.club_b)

    def test_cannot_choose_a_club_without_membership(self):
        from django.urls import reverse
        self.client.force_login(self.admin_b)
        self.assertEqual(self._choose(self.club_a).status_code, 404)
        session = self.client.session
        session['club_id'] = self.club_a.pk
        session.save()
        response = self.client.get(reverse('formation-list'))
        self.assertEqual(response.wsgi_request.club, self.club_b)
        # Un seul club : pas de sélecteur.
        self.assertNotContains(response, 'club-switcher')

    def test_superuser_reaches_every_club_as_admin(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        root = get_user_model().objects.create_superuser('root', 'root@example.com', 'pwd')
        self.client.force_login(root)
        self._choose(self.club_b)
        self.assertEqual(self.client.get(reverse('userManagement:user_list')).status_code, 200)
        self.assertContains(self.client.get(reverse('formation-list')), 'club-switcher')

    def test_account_without_club(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        self.client.force_login(get_user_model().objects.create_user('seul', 'seul@example.com', 'pwd'))
        self.assertContains(self.client.get(reverse('home')), "n'est rattaché à aucun club")
        self.assertRedirects(self.client.get(reverse('suivi-sessions')), reverse('home'))

    def test_staff_choices_limited_to_club(self):
        from django.urls import reverse
        self.client.force_login(self.admin_b)
        response = self.client.get(reverse('suivi-session-create'))
        self.assertContains(response, 'moniteur_b')
        self.assertNotContains(response, 'moniteur_a')
        self.assertNotContains(self.client.get(reverse('formation-create')), 'moniteur_a')

    def test_users_page_lists_only_club_members(self):
        from django.urls import reverse
        self.client.force_login(self.admin_b)
        response = self.client.get(reverse('userManagement:user_list'))
        self.assertContains(response, 'moniteur_b')
        self.assertNotContains(response, 'moniteur_a')
        # Compte partagé : retiré du club, jamais supprimé ni réinitialisé depuis ce club.
        self.assertContains(response, 'Retirer du club')
        self.assertEqual(self.client.get(
            reverse('userManagement:user_role', args=[self.instructor_a.pk])).status_code, 404)

    def test_new_student_with_email_of_another_club_account_shares_it(self):
        from django.urls import reverse
        from .models import Membership
        self.client.force_login(self.instructor_b)
        response = self.client.post(reverse('eleve-create'), {
            'first_name': 'Marc', 'last_name': 'Moniteur', 'email': 'Moniteur_A@example.com',
        }, follow=True)
        fiche = Member.objects.get(club=self.club_b, last_name='Moniteur')
        self.assertEqual(fiche.user, self.instructor_a)
        self.assertContains(response, 'Un compte existe déjà pour cet email')
        self.assertNotContains(response, self.club_a.name)
        self.assertEqual(self.instructor_a.role_in(self.club_b), 'student')
        self.assertEqual(Membership.objects.get(user=self.instructor_a, club=self.club_a).role, 'instructor')
        # Compte partagé : email verrouillé, pas de réinitialisation depuis le club B.
        edit = self.client.get(reverse('eleve-edit', args=[fiche.pk]))
        self.assertTrue(edit.context['form'].fields['email'].disabled)
        self.assertFalse(self.client.get(reverse('suivi-student-detail', args=[fiche.pk])).context['can_reset_password'])
        # Supprimer la fiche du club B garde le compte et son rôle dans le club A.
        self.client.post(reverse('eleve-delete', args=[fiche.pk]))
        self.assertTrue(type(self.instructor_a).objects.filter(pk=self.instructor_a.pk).exists())
        self.assertFalse(Membership.objects.filter(user=self.instructor_a, club=self.club_b).exists())
        self.assertTrue(Membership.objects.filter(user=self.instructor_a, club=self.club_a).exists())

    def test_pending_invitation_of_another_club_is_never_shown(self):
        from django.urls import reverse
        from userManagement.views import create_invited_user
        pending = create_invited_user('nouveau@example.com', club=self.club_a, role='student')
        self.client.force_login(self.instructor_b)
        self.client.post(reverse('eleve-create'), {'first_name': 'N', 'last_name': 'Nouveau', 'email': 'nouveau@example.com'})
        fiche = Member.objects.get(club=self.club_b, last_name='Nouveau')
        self.assertEqual(fiche.user, pending)
        self.assertNotContains(self.client.get(reverse('suivi-student-detail', args=[fiche.pk])), str(pending.invite_token))
        self.client.force_login(self.admin_b)
        self.assertNotContains(self.client.get(reverse('userManagement:user_list')), str(pending.invite_token))

    def test_accounts_of_another_club_are_not_attachable(self):
        from django.urls import reverse
        self.client.force_login(self.instructor_b)
        response = self.client.get(reverse('eleve-create'))
        self.assertNotContains(response, 'moniteur_a@example.com')
        response = self.client.post(reverse('eleve-create'),
                                    {'first_name': 'A', 'last_name': 'B', 'account': self.instructor_a.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Member.objects.filter(user=self.instructor_a).exists())

    def test_invite_existing_account_adds_it_to_the_club(self):
        from django.urls import reverse
        self.client.force_login(self.admin_b)
        response = self.client.post(reverse('userManagement:invite'),
                                    {'email': 'moniteur_a@example.com', 'role': 'instructor'}, follow=True)
        self.assertContains(response, 'Un compte existe déjà')
        self.assertEqual(self.instructor_a.role_in(self.club_b), 'instructor')
        # Retirer du club B un compte qui sert aussi au club A : le compte reste.
        self.client.post(reverse('userManagement:user_delete', args=[self.instructor_a.pk]))
        self.assertTrue(type(self.instructor_a).objects.filter(pk=self.instructor_a.pk).exists())
        self.assertFalse(self.instructor_a.memberships.filter(club=self.club_b).exists())
        # Un compte du club B seulement est supprimé.
        self.client.post(reverse('userManagement:user_delete', args=[self.instructor_b.pk]))
        self.assertFalse(type(self.instructor_b).objects.filter(pk=self.instructor_b.pk).exists())

    def test_role_change_only_affects_active_club(self):
        from django.urls import reverse
        self.client.force_login(self.admin_b)
        self.client.post(reverse('userManagement:user_role', args=[self.paul.pk]), {'role': 'instructor'})
        roles = dict(self.paul.memberships.values_list('club_id', 'role'))
        self.assertEqual(roles, {self.club_a.pk: 'admin', self.club_b.pk: 'instructor'})
