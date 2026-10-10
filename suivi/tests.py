from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from formation.models import (
    Cursus, CursusCategory, Member, MemberSkill, Season, Skill, SkillEvaluation,
)
from .models import Attendance, Exercise, StudentNote, TrainingSession, WorkedSkill


class SuiviTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        for name in ['member', 'instructor', 'dive_director', 'admin']:
            Group.objects.get_or_create(name=name)
        cls.instructor = User.objects.create_user('moniteur', 'moniteur@example.com', 'pwd')
        cls.instructor.groups.add(Group.objects.get(name='instructor'))
        cls.student_user = User.objects.create_user('eleve', 'alice@example.com', 'pwd')
        cls.student_user.groups.add(Group.objects.get(name='member'))

        cls.season = Season.objects.create(label='2026-2027', current=True)
        cls.cursus = Cursus.objects.create(name='Niveau 1', date=date(2026, 1, 1))
        other_cursus = Cursus.objects.create(name='Niveau 2', date=date(2026, 1, 1))
        cat = CursusCategory.objects.create(cursus=cls.cursus, name='Technique')
        cls.skill_a = Skill.objects.create(category=cat, name='Vidage de masque', order=1)
        cls.skill_b = Skill.objects.create(category=cat, name='Lâcher / reprise embout', order=2)

        cls.alice = Member.objects.create(user=cls.student_user, first_name='Alice', last_name='Martin')
        cls.bob = Member.objects.create(first_name='Bob', last_name='Durand')
        cls.carol = Member.objects.create(first_name='Carol', last_name='Petit')
        cls.alice.formations.add(cls.cursus)
        cls.bob.formations.add(cls.cursus)
        cls.carol.formations.add(other_cursus)
        for m in [cls.alice, cls.bob, cls.carol]:
            m.seasons.add(cls.season)
        # Élève d'une autre saison : jamais attendu
        old = Member.objects.create(first_name='Dan', last_name='Ancien')
        old.formations.add(cls.cursus)
        old.seasons.add(Season.objects.create(label='2025-2026'))

    def setUp(self):
        self.client.force_login(self.instructor)

    def _create_session(self):
        resp = self.client.post(reverse('suivi-session-create'), {
            'date': '2026-10-07', 'title': 'Piscine', 'location': 'Bassin', 'cursus': [self.cursus.pk],
            'instructors': [self.instructor.pk], 'notes': '',
        })
        session = TrainingSession.objects.get()
        self.assertRedirects(resp, reverse('suivi-session-detail', args=[session.pk]))
        return session

    def test_session_create_and_roster(self):
        session = self._create_session()
        self.assertEqual(session.season, self.season)
        self.assertEqual(list(session.roster()), [self.bob, self.alice])
        resp = self.client.get(reverse('suivi-session-detail', args=[session.pk]))
        self.assertContains(resp, 'Alice')
        self.assertNotContains(resp, 'name="att_%d"' % self.carol.pk)

    def test_attendance_and_worked_skills_per_student(self):
        session = self._create_session()
        url = reverse('suivi-session-detail', args=[session.pk])
        self.client.post(url, {
            '_action': 'attendance',
            f'att_{self.alice.pk}': 'present',
            f'att_{self.bob.pk}': 'excused', f'att_{self.bob.pk}_comment': 'malade',
        })
        self.assertEqual(Attendance.objects.get(member=self.alice).status, 'present')
        self.assertEqual(Attendance.objects.get(member=self.bob).comment, 'malade')

        # Un participant hors niveau peut être ajouté
        self.client.post(url, {'_action': 'add_member', 'member_id': self.carol.pk})
        self.assertIn(self.carol, session.roster())

        # Alice : A travaillée et validée, B travaillée sans évaluation
        self.client.post(url, {
            '_action': 'worked_skills', 'member_id': self.alice.pk,
            f'ws_{self.skill_a.pk}_status': 'acquired',
            f'ws_{self.skill_b.pk}': '1', f'ws_{self.skill_b.pk}_status': '',
        })
        worked = {ws.skill: ws.status for ws in WorkedSkill.objects.filter(session=session, member=self.alice)}
        self.assertEqual(worked, {self.skill_a: 'acquired', self.skill_b: ''})
        self.assertEqual(MemberSkill.objects.get(member=self.alice, skill=self.skill_a).status, 'acquired')
        self.assertFalse(MemberSkill.objects.filter(member=self.alice, skill=self.skill_b).exists())
        self.assertEqual(SkillEvaluation.objects.get().date, session.date)
        self.assertEqual(SkillEvaluation.objects.get().author, self.instructor)
        self.assertEqual(WorkedSkill.objects.get(member=self.alice, skill=self.skill_b).author, self.instructor)
        self.assertContains(self.client.get(url), 'saisi par moniteur')

        # Les compétences sont propres à chaque élève
        self.assertFalse(WorkedSkill.objects.filter(member=self.bob).exists())

        # Ré-enregistrer à l'identique ne recrée pas d'évaluation ; décocher supprime
        self.client.post(url, {
            '_action': 'worked_skills', 'member_id': self.alice.pk,
            f'ws_{self.skill_a.pk}': '1', f'ws_{self.skill_a.pk}_status': 'acquired',
        })
        self.assertEqual(SkillEvaluation.objects.count(), 1)
        self.assertEqual(list(WorkedSkill.objects.values_list('skill', flat=True)), [self.skill_a.pk])

        resp = self.client.get(url)
        self.assertContains(resp, f'id="eleve-{self.alice.pk}"')
        self.assertNotContains(resp, f'id="eleve-{self.bob.pk}"')  # excusé, rien de saisi

        # Désélectionner un statut supprime la présence
        self.client.post(url, {'_action': 'attendance', f'att_{self.alice.pk}': 'present'})
        self.assertFalse(Attendance.objects.filter(member=self.bob).exists())

    def test_overview_and_student_pages(self):
        session = self._create_session()
        Attendance.objects.create(session=session, member=self.alice, status='present')
        WorkedSkill.objects.create(session=session, member=self.alice, skill=self.skill_a, status='in_progress')

        resp = self.client.get(reverse('suivi-attendance'))
        self.assertContains(resp, 'Martin Alice')
        self.assertContains(resp, '100 %')
        resp = self.client.get(reverse('suivi-students'))
        self.assertContains(resp, 'Martin Alice')
        self.assertEqual(self.client.get(reverse('suivi-sessions')).status_code, 200)

        resp = self.client.get(reverse('suivi-student-detail', args=[self.alice.pk]))
        self.assertContains(resp, '1 séance')
        self.assertContains(resp, 'Vidage de masque <span class="badge badge-in_progress">')

    def test_exercises_and_notes(self):
        url = reverse('suivi-student-detail', args=[self.alice.pk])
        self.client.post(url, {
            '_action': 'add_exercise', 'date': '2026-10-07', 'name': 'Remontée 6 m',
            'skill': self.skill_a.pk, 'result': 'partial', 'comment': '',
        })
        self.assertEqual(Exercise.objects.get().author, self.instructor)
        self.client.post(url, {'_action': 'add_note', 'date': '2026-10-07', 'content': 'Privé', 'visibility': 'staff'})
        self.client.post(url, {'_action': 'add_note', 'date': '2026-10-07', 'content': 'Bravo !', 'visibility': 'student'})
        self.assertEqual(StudentNote.objects.count(), 2)
        resp = self.client.get(url)
        self.assertContains(resp, 'Remontée 6 m')
        self.assertContains(resp, 'Privé')

        # L'élève ne voit que les notes qui lui sont destinées
        self.client.force_login(self.student_user)
        resp = self.client.get(reverse('suivi-mine'))
        self.assertContains(resp, 'Bravo !')
        self.assertContains(resp, 'Remontée 6 m')
        self.assertNotContains(resp, 'Privé')

        note = StudentNote.objects.get(content='Privé')
        self.client.force_login(self.instructor)
        self.client.post(url, {'_action': 'toggle_note', 'note_pk': note.pk})
        note.refresh_from_db()
        self.assertEqual(note.visibility, 'student')

    def test_students_cannot_access_staff_pages(self):
        session = self._create_session()
        self.client.force_login(self.student_user)
        for name, args in [
            ('suivi-sessions', []), ('suivi-attendance', []), ('suivi-students', []),
            ('suivi-session-detail', [session.pk]), ('suivi-student-detail', [self.alice.pk]),
        ]:
            self.assertRedirects(self.client.get(reverse(name, args=args)), reverse('home'), fetch_redirect_response=False)
        resp = self.client.post(reverse('suivi-student-detail', args=[self.alice.pk]), {
            '_action': 'add_note', 'date': '2026-10-07', 'content': 'x', 'visibility': 'student',
        })
        self.assertFalse(StudentNote.objects.exists())

    def test_delete_session(self):
        session = self._create_session()
        Attendance.objects.create(session=session, member=self.alice, status='present')
        self.client.post(reverse('suivi-session-delete', args=[session.pk]))
        self.assertFalse(TrainingSession.objects.exists())
        self.assertFalse(Attendance.objects.exists())

    def test_evaluation_page_traces_status_changes_with_author(self):
        url = reverse('eleve-evaluation-save', args=[self.alice.pk, self.cursus.pk])
        # Changement de statut sans commentaire : historisé avec l'auteur
        self.client.post(url, {f'skill_{self.skill_a.pk}_status': 'in_progress'})
        ev = SkillEvaluation.objects.get()
        self.assertEqual((ev.skill, ev.status, ev.author), (self.skill_a, 'in_progress', self.instructor))
        # Ré-enregistrer sans changement ni commentaire : pas de nouvelle entrée
        self.client.post(url, {f'skill_{self.skill_a.pk}_status': 'in_progress'})
        self.assertEqual(SkillEvaluation.objects.count(), 1)

        resp = self.client.get(reverse('eleve-evaluation', args=[self.alice.pk]))
        self.assertContains(resp, 'par moniteur')
        resp = self.client.get(reverse('suivi-student-detail', args=[self.alice.pk]))
        self.assertContains(resp, ' · moniteur')
        resp = self.client.get(reverse('eleve-evaluation-export', args=[self.alice.pk, self.cursus.pk]))
        self.assertEqual(resp['Content-Type'], 'application/pdf')

    def test_create_student_creates_invited_account(self):
        resp = self.client.post(reverse('eleve-create'), {
            'first_name': 'Eve', 'last_name': 'Nouvelle', 'email': 'Eve@Example.com',
            'formations': [self.cursus.pk], 'seasons': [self.season.pk],
        })
        eve = Member.objects.get(first_name='Eve')
        self.assertRedirects(resp, reverse('suivi-student-detail', args=[eve.pk]))
        self.assertEqual(eve.email, 'eve@example.com')
        self.assertFalse(eve.user.is_active)
        self.assertTrue(eve.user.groups.filter(name='member').exists())

        resp = self.client.get(reverse('suivi-student-detail', args=[eve.pk]))
        accept_url = reverse('userManagement:accept_invite', args=[eve.user.invite_token])
        self.assertContains(resp, accept_url)

        # L'élève active son compte puis voit sa fiche
        self.client.logout()
        self.client.post(accept_url, {'username': 'eve', 'password1': 'S3cret-pass!', 'password2': 'S3cret-pass!'})
        resp = self.client.get(reverse('suivi-mine'))
        self.assertContains(resp, 'Mon suivi')
        self.assertContains(resp, 'Niveau 1')

    def test_student_email_must_be_unique_among_students(self):
        resp = self.client.post(reverse('eleve-create'), {
            'first_name': 'X', 'last_name': 'Y', 'email': 'alice@example.com', 'seasons': [self.season.pk],
        })
        self.assertContains(resp, 'déjà utilisée par un autre élève')
        self.assertFalse(Member.objects.filter(first_name='X').exists())

    def test_edit_student_and_renew_invite(self):
        url = reverse('eleve-edit', args=[self.bob.pk])
        self.client.post(url, {'first_name': 'Bob', 'last_name': 'Durand', 'email': 'bob@example.com',
                               'formations': [self.cursus.pk], 'seasons': [self.season.pk]})
        self.bob.refresh_from_db()
        self.assertEqual(self.bob.email, 'bob@example.com')
        token = self.bob.user.invite_token
        self.client.post(url, {'_action': 'renew_invite'})
        self.bob.user.refresh_from_db()
        self.assertNotEqual(self.bob.user.invite_token, token)

    def test_my_tracking_without_profile(self):
        self.client.force_login(self.instructor)
        resp = self.client.get(reverse('suivi-mine'))
        self.assertContains(resp, 'Aucune fiche élève')

    def test_admin_pages_render(self):
        admin = get_user_model().objects.create_user('chef', 'chef@example.com', 'pwd')
        admin.groups.add(Group.objects.get(name='admin'))
        self.client.force_login(admin)
        for name, args in [
            ('home', []), ('saison-gestion', []), ('saison-formation', []), ('saison-cursus-creer', []),
            ('saison-cursus-importer', []), ('saison-cursus-detail', [self.cursus.pk]),
            ('eleve-create', []), ('eleve-edit', [self.alice.pk]), ('suivi-sessions', []),
        ]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200, name)
        # Les formateurs n'ont pas accès à la gestion des saisons et formations
        self.client.force_login(self.instructor)
        self.assertRedirects(self.client.get(reverse('saison-gestion')), reverse('home'), fetch_redirect_response=False)

    def test_students_cannot_access_management_or_evaluation(self):
        self.client.force_login(self.student_user)
        for name, args in [
            ('saison-gestion', []), ('saison-formation', []), ('saison-cursus-detail', [self.cursus.pk]),
            ('eleve-create', []), ('eleve-edit', [self.alice.pk]), ('eleve-evaluation', [self.alice.pk]),
            ('eleve-evaluation-save', [self.alice.pk, self.cursus.pk]),
            ('eleve-evaluation-export', [self.alice.pk, self.cursus.pk]),
        ]:
            for method in (self.client.get, self.client.post):
                resp = method(reverse(name, args=args))
                self.assertRedirects(resp, reverse('home'), fetch_redirect_response=False, msg_prefix=name)
        self.assertFalse(MemberSkill.objects.exists())
