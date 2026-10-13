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
        from django.contrib.auth.models import Group

        from formation.models import CursusCategory, Enrollment, Skill, SkillEvaluation
        from suivi.models import Attendance, Comment

        cls.admin = get_user_model().objects.create_user('admin', 'admin@example.com', 'pwd')
        cls.admin.groups.add(Group.objects.get(name='admin'))

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
