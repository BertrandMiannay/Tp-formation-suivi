from django.conf import settings
from django.db import models

from formation.models import Enrollment, Formation, Member, MemberSkill, Season, Skill, SkillEvaluation


class TrainingSession(models.Model):
    """Séance hebdomadaire de formation."""

    season      = models.ForeignKey(Season, null=True, blank=True, on_delete=models.SET_NULL, related_name='training_sessions')
    date        = models.DateField()
    title       = models.CharField(max_length=200, blank=True, help_text="Thème de la séance (facultatif)")
    location    = models.CharField(max_length=200, blank=True)
    formations  = models.ManyToManyField(Formation, blank=True, related_name='training_sessions',
                                         help_text="Formations travaillées pendant la séance")
    instructors = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='training_sessions')
    notes       = models.TextField(blank=True, help_text="Déroulé / remarques (visibles par l'équipe encadrante uniquement)")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Séance'
        verbose_name_plural = 'Séances'
        ordering            = ['-date', '-pk']

    def __str__(self):
        label = f"Séance du {self.date:%d/%m/%Y}"
        return f"{label} — {self.title}" if self.title else label

    def roster(self):
        """Élèves attendus : inscrits (en formation) à l'une des formations de la séance,
        plus toute personne ayant déjà une présence enregistrée."""
        expected = Enrollment.objects.filter(
            formation__in=self.formations.all(), status=Enrollment.Status.ACTIVE,
        ).values_list('member_id', flat=True)
        recorded = self.attendances.values_list('member_id', flat=True)
        return (
            Member.objects
            .filter(models.Q(pk__in=expected) | models.Q(pk__in=recorded))
            .distinct()
            .order_by('last_name', 'first_name')
        )


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = 'present', 'Présent'
        ABSENT  = 'absent',  'Absent'

    session = models.ForeignKey(TrainingSession, on_delete=models.CASCADE, related_name='attendances')
    member  = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='attendances')
    status  = models.CharField(max_length=20, choices=Status.choices)
    comment = models.CharField(max_length=255, blank=True)
    staff_comment = models.CharField('Note équipe', max_length=255, blank=True,
                                     help_text="Réservée à l'équipe encadrante : jamais affichée à l'élève.")

    class Meta:
        verbose_name        = 'Présence'
        verbose_name_plural = 'Présences'
        constraints = [
            models.UniqueConstraint(fields=['session', 'member'], name='unique_session_attendance'),
        ]

    def __str__(self):
        return f"{self.member} — {self.session} : {self.get_status_display()}"


class WorkedSkill(models.Model):
    """Compétence travaillée par un élève lors d'une séance, avec l'évaluation donnée ce jour-là."""

    session = models.ForeignKey(TrainingSession, on_delete=models.CASCADE, related_name='worked_skills')
    member  = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='worked_skills')
    skill   = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='worked_skills')
    status  = models.CharField(max_length=20, choices=MemberSkill.SkillStatus.choices, blank=True,
                               help_text="Évaluation lors de la séance (vide = travaillée sans évaluation)")
    comment = models.CharField(max_length=255, blank=True)
    staff_comment = models.CharField('Note équipe', max_length=255, blank=True,
                                     help_text="Réservée à l'équipe encadrante : jamais affichée à l'élève.")
    author  = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='+', verbose_name='Saisi par')
    # Évaluation de l'historique créée par cette saisie : mise à jour quand la séance est ressaisie,
    # supprimée quand l'évaluation du jour est retirée (le statut de l'élève est alors recalculé).
    evaluation = models.OneToOneField(SkillEvaluation, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name='worked_skill', verbose_name='Évaluation')

    class Meta:
        verbose_name        = 'Compétence travaillée'
        verbose_name_plural = 'Compétences travaillées'
        constraints = [
            models.UniqueConstraint(fields=['session', 'member', 'skill'], name='unique_worked_skill'),
        ]

    def __str__(self):
        return f"{self.member} — {self.skill} ({self.session.date:%d/%m/%Y})"


class StudentNote(models.Model):
    """Note sur un élève : partie visible par l'élève et/ou note réservée à l'équipe."""

    member     = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='student_notes')
    session    = models.ForeignKey(TrainingSession, null=True, blank=True, on_delete=models.SET_NULL, related_name='student_notes')
    date       = models.DateField()
    content    = models.TextField('Note', blank=True, help_text="Visible par l'élève dans « Mon suivi ».")
    staff_content = models.TextField('Note équipe', blank=True,
                                     help_text="Réservée à l'équipe encadrante : jamais affichée à l'élève.")
    author     = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Note élève'
        verbose_name_plural = 'Notes élèves'
        ordering            = ['-date', '-pk']

    def __str__(self):
        return f"{self.member} — {self.date:%d/%m/%Y}"
