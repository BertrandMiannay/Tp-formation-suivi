from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from formation.models import (
    Cursus, CursusCategory, Enrollment, Formation, Member, MemberSkill, Season, Skill, SkillEvaluation,
)
from .models import Attendance, Exercise, StudentNote, TrainingSession, WorkedSkill


class SuiviFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.instructor = User.objects.create_user('moniteur', 'moniteur@example.com', 'pwd')
        cls.instructor.groups.add(Group.objects.get(name='instructor'))
        cls.student_user = User.objects.create_user('eleve', 'alice@example.com', 'pwd')
        cls.student_user.groups.add(Group.objects.get(name='student'))

        cls.season = Season.objects.create(label='2026-2027', current=True)
        cls.cursus = Cursus.objects.create(name='Niveau 1', date=date(2026, 1, 1))
        other_cursus = Cursus.objects.create(name='Niveau 2', date=date(2026, 1, 1))
        cat = CursusCategory.objects.create(cursus=cls.cursus, name='Technique')
        cls.skill_a = Skill.objects.create(category=cat, name='Vidage de masque', order=1)
        cls.skill_b = Skill.objects.create(category=cat, name='Lâcher / reprise embout', order=2)

        cls.alice = Member.objects.create(user=cls.student_user, first_name='Alice', last_name='Martin')
        cls.bob = Member.objects.create(first_name='Bob', last_name='Durand')
        cls.carol = Member.objects.create(first_name='Carol', last_name='Petit')
        cls.formation = Formation.objects.create(name='N1 promo 2027', cursus=cls.cursus)
        other_formation = Formation.objects.create(name='N2 promo 2027', cursus=other_cursus)
        for m in [cls.alice, cls.bob]:
            Enrollment.objects.create(member=m, formation=cls.formation)
        Enrollment.objects.create(member=cls.carol, formation=other_formation)
        # Élève ayant abandonné : jamais attendu
        old = Member.objects.create(first_name='Dan', last_name='Ancien')
        Enrollment.objects.create(member=old, formation=cls.formation, status=Enrollment.Status.DROPPED)

    def setUp(self):
        self.client.force_login(self.instructor)

    def _create_session(self):
        resp = self.client.post(reverse('suivi-session-create'), {
            'date': '2026-10-07', 'title': 'Piscine', 'location': 'Bassin', 'formations': [self.formation.pk],
            'instructors': [self.instructor.pk], 'notes': '',
        })
        session = TrainingSession.objects.get()
        self.assertRedirects(resp, reverse('suivi-session-detail', args=[session.pk]))
        return session


class SuiviTestCase(SuiviFixtures):
    def test_session_create_and_roster(self):
        session = self._create_session()
        self.assertEqual(session.season, self.season)
        self.assertEqual(list(session.roster()), [self.bob, self.alice])
        resp = self.client.get(reverse('suivi-session-detail', args=[session.pk]))
        self.assertContains(resp, 'Alice')
        self.assertNotContains(resp, 'name="att_%d"' % self.carol.pk)

    def test_session_without_season_attached_when_season_activated(self):
        Season.objects.update(current=False)
        session = self._create_session()
        self.assertIsNone(session.season)
        self.assertContains(self.client.get(reverse('suivi-sessions')), 'Piscine')

        admin = get_user_model().objects.create_user('admin2', 'admin2@example.com', 'pwd')
        admin.groups.add(Group.objects.get(name='admin'))
        self.client.force_login(admin)
        self.client.post(reverse('saison-set-current', args=[self.season.pk]))
        session.refresh_from_db()
        self.assertEqual(session.season, self.season)
        self.assertContains(self.client.get(reverse('suivi-sessions')), 'Piscine')

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

        # Un participant d'une autre formation peut être ajouté
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

        resp = self.client.get(reverse('suivi-students') + '?vue=presences')
        self.assertContains(resp, 'Martin Alice')
        self.assertContains(resp, '100 %')
        self.assertContains(resp, 'class="att-card"')
        # L'ancienne page « Présences » redirige vers la vue présences de la liste des élèves
        self.assertRedirects(
            self.client.get(reverse('suivi-attendance') + f'?formation={self.formation.pk}'),
            reverse('suivi-students') + f'?vue=presences&formation={self.formation.pk}',
        )
        resp = self.client.get(reverse('formation-detail', args=[self.formation.pk]))
        self.assertContains(resp, 'id="presences"')
        self.assertContains(resp, '1/1 · 100 %')
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
        self.client.post(reverse('suivi-student-detail', args=[self.alice.pk]), {
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
            'formation': self.formation.pk,
        })
        eve = Member.objects.get(first_name='Eve')
        self.assertRedirects(resp, reverse('suivi-student-detail', args=[eve.pk]))
        self.assertEqual(eve.email, 'eve@example.com')
        self.assertTrue(Enrollment.objects.filter(member=eve, formation=self.formation).exists())
        self.assertFalse(eve.user.is_active)
        self.assertTrue(eve.user.groups.filter(name='student').exists())

        resp = self.client.get(reverse('suivi-student-detail', args=[eve.pk]))
        accept_url = reverse('userManagement:accept_invite', args=[eve.user.invite_token])
        self.assertContains(resp, accept_url)

        # L'élève active son compte puis voit sa fiche
        self.client.logout()
        self.client.post(accept_url, {'username': 'eve', 'password1': 'S3cret-pass!', 'password2': 'S3cret-pass!'})
        resp = self.client.get(reverse('suivi-mine'))
        self.assertContains(resp, 'Mon suivi')
        self.assertContains(resp, 'N1 promo 2027')

    def test_student_email_must_be_unique_among_students(self):
        resp = self.client.post(reverse('eleve-create'), {
            'first_name': 'X', 'last_name': 'Y', 'email': 'alice@example.com',
        })
        self.assertContains(resp, 'déjà utilisée par un autre élève')
        self.assertFalse(Member.objects.filter(first_name='X').exists())

    def test_edit_student_and_renew_invite(self):
        url = reverse('eleve-edit', args=[self.bob.pk])
        self.client.post(url, {'first_name': 'Bob', 'last_name': 'Durand', 'email': 'bob@example.com'})
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
            ('home', []), ('saison-gestion', []), ('saison-cursus', []), ('saison-cursus-creer', []),
            ('formation-list', []), ('formation-create', []), ('formation-detail', [self.formation.pk]),
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
            ('saison-gestion', []), ('saison-cursus', []), ('saison-cursus-detail', [self.cursus.pk]),
            ('eleve-create', []), ('eleve-edit', [self.alice.pk]), ('eleve-evaluation', [self.alice.pk]),
            ('formation-list', []), ('formation-create', []), ('formation-detail', [self.formation.pk]),
            ('eleve-evaluation-save', [self.alice.pk, self.cursus.pk]),
            ('eleve-evaluation-export', [self.alice.pk, self.cursus.pk]),
        ]:
            for method in (self.client.get, self.client.post):
                resp = method(reverse(name, args=args))
                self.assertRedirects(resp, reverse('home'), fetch_redirect_response=False, msg_prefix=name)
        self.assertFalse(MemberSkill.objects.exists())


class FormationWorkflowTestCase(SuiviFixtures):
    """Formation → inscriptions → séance → validation, avec des élèves sans compte."""

    def _admin(self):
        admin = get_user_model().objects.create_user('chef', 'chef@example.com', 'pwd')
        admin.groups.add(Group.objects.get(name='admin'))
        return admin

    def test_admin_creates_formation_instructor_cannot(self):
        data = {'name': 'N1 promo 2028', 'cursus': self.cursus.pk, 'start_date': '2027-09-01',
                'end_date': '2028-06-30', 'managers': [self.instructor.pk]}
        self.client.post(reverse('formation-create'), data)
        self.assertFalse(Formation.objects.filter(name='N1 promo 2028').exists())

        self.client.force_login(self._admin())
        resp = self.client.post(reverse('formation-create'), data)
        formation = Formation.objects.get(name='N1 promo 2028')
        self.assertRedirects(resp, reverse('formation-detail', args=[formation.pk]))
        self.assertEqual(list(formation.managers.all()), [self.instructor])

        resp = self.client.post(reverse('formation-create'), {**data, 'name': 'X', 'end_date': '2027-01-01'})
        self.assertContains(resp, 'postérieure au début')

    def test_enrollments_from_formation_page(self):
        url = reverse('formation-detail', args=[self.formation.pk])
        self.client.post(url, {'_action': 'create_student', 'first_name': 'Fred', 'last_name': 'Sanscompte'})
        fred = Member.objects.get(first_name='Fred')
        self.assertIsNone(fred.user)
        self.assertTrue(Enrollment.objects.filter(member=fred, formation=self.formation).exists())

        self.client.post(url, {'_action': 'enroll', 'member_id': self.carol.pk})
        enrollment = Enrollment.objects.get(member=self.carol, formation=self.formation)
        self.client.post(url, {'_action': 'set_status', 'enrollment_pk': enrollment.pk, 'status': 'completed'})
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, 'completed')

        resp = self.client.get(url)
        self.assertContains(resp, 'Sanscompte Fred')
        self.assertContains(resp, 'sans compte')

        self.client.post(url, {'_action': 'unenroll', 'enrollment_pk': enrollment.pk})
        self.assertFalse(Enrollment.objects.filter(pk=enrollment.pk).exists())

        # Un encadrant ne peut pas modifier ni clôturer la formation
        self.client.post(url, {'_action': 'toggle_status'})
        self.formation.refresh_from_db()
        self.assertEqual(self.formation.status, 'active')

    def test_student_without_account_in_session(self):
        session = self._create_session()
        url = reverse('suivi-session-detail', args=[session.pk])
        self.client.post(url, {'_action': 'create_student', 'first_name': 'Gina', 'last_name': 'Nouvelle',
                               'formation_id': self.formation.pk})
        gina = Member.objects.get(first_name='Gina')
        self.assertIsNone(gina.user)
        self.assertEqual(Attendance.objects.get(member=gina).status, 'present')
        self.assertIn(gina, session.roster())

        # Ses compétences se valident comme pour les autres élèves
        self.client.post(url, {'_action': 'worked_skills', 'member_id': gina.pk,
                               f'ws_{self.skill_a.pk}_status': 'acquired'})
        self.assertEqual(MemberSkill.objects.get(member=gina, skill=self.skill_a).status, 'acquired')

        # Compte créé plus tard en renseignant l'email
        self.client.post(reverse('eleve-edit', args=[gina.pk]), {'first_name': 'Gina', 'last_name': 'Nouvelle',
                                                                 'email': 'gina@example.com'})
        gina.refresh_from_db()
        self.assertFalse(gina.user.is_active)
        self.assertTrue(gina.user.groups.filter(name='student').exists())

    def test_create_student_without_email(self):
        resp = self.client.post(reverse('eleve-create'), {'first_name': 'Hugo', 'last_name': 'Libre'})
        hugo = Member.objects.get(first_name='Hugo')
        self.assertRedirects(resp, reverse('suivi-student-detail', args=[hugo.pk]))
        self.assertIsNone(hugo.user)
        self.assertFalse(Enrollment.objects.filter(member=hugo).exists())
        # Visible dans « Tous les élèves », pas dans « En formation »
        self.assertNotContains(self.client.get(reverse('suivi-students')), 'Libre Hugo')
        self.assertContains(self.client.get(reverse('suivi-students') + '?formation=all'), 'Libre Hugo')
        # Inscription depuis la fiche
        self.client.post(reverse('suivi-student-detail', args=[hugo.pk]),
                         {'_action': 'enroll', 'formation_id': self.formation.pk})
        self.assertTrue(Enrollment.objects.filter(member=hugo, formation=self.formation).exists())

    def test_email_cannot_be_removed_once_account_exists(self):
        resp = self.client.post(reverse('eleve-edit', args=[self.alice.pk]),
                                {'first_name': 'Alice', 'last_name': 'Martin', 'email': ''})
        self.assertContains(resp, 'ne peut pas être retiré')

    def test_student_account_is_read_only(self):
        self.client.force_login(self.student_user)
        resp = self.client.get(reverse('suivi-mine'))
        self.assertContains(resp, 'N1 promo 2027')
        self.assertNotContains(resp, '<form')
        url = reverse('formation-detail', args=[self.formation.pk])
        self.client.post(url, {'_action': 'create_student', 'first_name': 'Z', 'last_name': 'Z'})
        self.assertFalse(Member.objects.filter(first_name='Z').exists())


class StudentAccountSecurityTests(SuiviFixtures):
    STUDENT_FORM = {'first_name': 'Eve', 'last_name': 'Admin', 'birthdate': '', 'medical_certificate_date': '',
                    'emergency_contact_name': '', 'emergency_contact_phone': ''}

    def test_staff_account_email_not_editable_from_student_sheet(self):
        admin = get_user_model().objects.create_user('chef', 'chef@example.com', 'pwd')
        admin.groups.add(Group.objects.get(name='admin'))
        self.client.post(reverse('eleve-create'), {**self.STUDENT_FORM, 'email': 'chef@example.com'})
        member = Member.objects.get(first_name='Eve')
        self.assertEqual(member.user, admin)  # rattachement conservé (admin qui suit une formation)
        self.client.post(reverse('eleve-edit', args=[member.pk]), {**self.STUDENT_FORM, 'email': 'pirate@example.com'})
        admin.refresh_from_db()
        self.assertEqual(admin.email, 'chef@example.com')

    def test_student_account_email_follows_sheet(self):
        self.client.post(reverse('eleve-edit', args=[self.alice.pk]), {
            **self.STUDENT_FORM, 'first_name': 'Alice', 'last_name': 'Martin', 'email': 'alice.martin@example.com',
        })
        self.student_user.refresh_from_db()
        self.assertEqual(self.student_user.email, 'alice.martin@example.com')

    def test_pdf_export_with_markup_in_names(self):
        self.skill_a.name = 'Remontée < 6 m & palier'
        self.skill_a.save()
        resp = self.client.get(reverse('eleve-evaluation-export', args=[self.alice.pk, self.cursus.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')

    def test_attendance_redirect_encodes_formation(self):
        resp = self.client.get(reverse('suivi-attendance'), {'formation': '1&vue=liste'})
        self.assertRedirects(resp, reverse('suivi-students') + '?vue=presences&formation=1%26vue%3Dliste',
                             fetch_redirect_response=False)


class StudentFromAccountTests(SuiviFixtures):
    def setUp(self):
        super().setUp()
        self.account = get_user_model().objects.create_user(
            'jdupont', 'jean@example.com', 'pwd', first_name='Jean', last_name='Dupont')
        self.account.groups.add(Group.objects.get(name='instructor'))

    def test_prefill_from_user_param(self):
        resp = self.client.get(reverse('eleve-create'), {'user': self.account.pk})
        form = resp.context['form']
        self.assertEqual(form.initial['first_name'], 'Jean')
        self.assertEqual(form.initial['last_name'], 'Dupont')
        self.assertTrue(form.fields['email'].disabled)
        self.assertContains(resp, 'jean@example.com')

    def test_accounts_with_sheet_are_not_offered(self):
        form = self.client.get(reverse('eleve-create')).context['form']
        offered = set(form.fields['account'].queryset)
        self.assertIn(self.account, offered)
        self.assertNotIn(self.student_user, offered)  # Alice a déjà sa fiche
        # ?user= d'un compte qui a déjà une fiche : ignoré
        form = self.client.get(reverse('eleve-create'), {'user': self.student_user.pk}).context['form']
        self.assertFalse(form.fields['email'].disabled)

    def test_create_links_chosen_account(self):
        self.client.post(reverse('eleve-create'), {
            'account': self.account.pk, 'first_name': 'Jean', 'last_name': 'Dupont',
            'email': 'autre@example.com', 'formation': self.formation.pk,
        })
        member = Member.objects.get(first_name='Jean')
        self.assertEqual(member.user, self.account)
        self.account.refresh_from_db()
        self.assertEqual(self.account.email, 'jean@example.com')
        self.assertTrue(Enrollment.objects.filter(member=member, formation=self.formation).exists())

    def test_account_without_email_is_linked(self):
        self.account.email = ''
        self.account.save()
        self.client.post(reverse('eleve-create'), {'account': self.account.pk, 'first_name': 'Jean', 'last_name': 'Dupont'})
        self.assertEqual(Member.objects.get(first_name='Jean').user, self.account)

    def test_account_with_sheet_is_rejected(self):
        resp = self.client.post(reverse('eleve-create'), {
            'account': self.student_user.pk, 'first_name': 'Alice', 'last_name': 'Bis'})
        self.assertIn('account', resp.context['form'].errors)
        self.assertFalse(Member.objects.filter(last_name='Bis').exists())


class StudentImportDeleteTests(SuiviFixtures):
    def test_import_students_with_enrollment_and_accounts(self):
        resp = self.client.post(reverse('eleve-import'), {
            'lines': "Nom;Prénom;Email\nLeroy;Emma;Emma@Example.com\nRoux\tHugo\n\nBlanc, Inès, ",
            'formation': self.formation.pk,
        })
        self.assertRedirects(resp, reverse('formation-detail', args=[self.formation.pk]) + '#eleves',
                             fetch_redirect_response=False)
        emma = Member.objects.get(first_name='Emma', last_name='Leroy')
        self.assertEqual(emma.email, 'emma@example.com')
        self.assertFalse(emma.user.is_active)
        self.assertTrue(emma.user.groups.filter(name='student').exists())
        for first, last in [('Hugo', 'Roux'), ('Inès', 'Blanc')]:
            member = Member.objects.get(first_name=first, last_name=last)
            self.assertIsNone(member.user)
        self.assertEqual(Enrollment.objects.filter(formation=self.formation, member__first_name__in=['Emma', 'Hugo', 'Inès']).count(), 3)

    def test_import_rejects_all_on_error(self):
        resp = self.client.post(reverse('eleve-import'), {
            'lines': "Leroy;Emma;emma@example.com\nSeul\nX;Y;pas-un-email\nZ;W;alice@example.com\nV;U;EMMA@example.com",
        })
        self.assertEqual(resp.status_code, 200)
        for msg in ['Ligne 2', 'Ligne 3 : adresse email invalide', 'Ligne 4 : alice@example.com est déjà utilisée',
                    'Ligne 5 : emma@example.com apparaît plusieurs fois']:
            self.assertContains(resp, msg)
        self.assertFalse(Member.objects.filter(first_name='Emma').exists())

    def test_delete_student_and_student_account(self):
        self.client.get(reverse('eleve-edit', args=[self.alice.pk]))
        resp = self.client.post(reverse('eleve-delete', args=[self.alice.pk]))
        self.assertRedirects(resp, reverse('suivi-students'), fetch_redirect_response=False)
        self.assertFalse(Member.objects.filter(pk=self.alice.pk).exists())
        self.assertFalse(Enrollment.objects.filter(member_id=self.alice.pk).exists())
        self.assertFalse(get_user_model().objects.filter(pk=self.student_user.pk).exists())

    def test_delete_student_keeps_staff_account(self):
        member = Member.objects.create(user=self.instructor, first_name='Mo', last_name='Niteur')
        resp = self.client.get(reverse('eleve-edit', args=[member.pk]))
        self.assertContains(resp, 'est conservé')
        self.client.post(reverse('eleve-delete', args=[member.pk]))
        self.assertFalse(Member.objects.filter(pk=member.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.instructor.pk).exists())

    def test_delete_requires_post_and_staff(self):
        self.client.get(reverse('eleve-delete', args=[self.bob.pk]))
        self.assertTrue(Member.objects.filter(pk=self.bob.pk).exists())
        self.client.force_login(self.student_user)
        self.client.post(reverse('eleve-delete', args=[self.bob.pk]))
        self.assertTrue(Member.objects.filter(pk=self.bob.pk).exists())
