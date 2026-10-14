from django.conf import settings
from django.db import models
from django.utils import timezone

from clubs.models import Club, get_default_club


class Season(models.Model):
    club = models.ForeignKey(Club, on_delete=models.CASCADE, default=get_default_club, related_name='seasons',
                             verbose_name='Club')
    label = models.CharField(max_length=20)
    current = models.BooleanField(default=False)

    def __str__(self):
        return self.label

    class Meta:
        verbose_name = 'Saison'
        verbose_name_plural = 'Saisons'


class Cursus(models.Model):
    class Status(models.TextChoices):
        ACTIVE   = 'active',   'Actif'
        ARCHIVED = 'archived', 'Archivé'

    club = models.ForeignKey(Club, on_delete=models.CASCADE, default=get_default_club, related_name='cursus',
                             verbose_name='Club')
    name   = models.CharField(max_length=200)
    date   = models.DateField(help_text="Date de version du cursus")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        verbose_name        = 'Cursus'
        verbose_name_plural = 'Cursus'
        ordering            = ['-date']

    def __str__(self):
        return self.name

    @classmethod
    def in_use_ids(cls):
        """Cursus non supprimables : un élève est inscrit à l'une de leurs formations (quel que soit le statut)
        ou a déjà un suivi (statut, évaluation, compétence travaillée, commentaire) sur l'une de leurs compétences."""
        from suivi.models import Comment, WorkedSkill
        ids = set(Enrollment.objects.values_list('formation__cursus_id', flat=True).distinct())
        for model in (MemberSkill, SkillEvaluation, WorkedSkill, Comment):
            ids.update(model.objects.values_list('skill__category__cursus_id', flat=True).distinct())
        return ids

    def is_deletable(self):
        from suivi.models import Comment, WorkedSkill
        return not (
            Enrollment.objects.filter(formation__cursus=self).exists()
            or any(model.objects.filter(skill__category__cursus=self).exists()
                   for model in (MemberSkill, SkillEvaluation, WorkedSkill, Comment))
        )


class CursusCategory(models.Model):
    cursus = models.ForeignKey(Cursus, on_delete=models.CASCADE, related_name='categories')
    name   = models.CharField(max_length=200)
    order  = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Catégorie'
        verbose_name_plural = 'Catégories'
        ordering            = ['order', 'pk']

    def __str__(self):
        return f"{self.cursus.name} — {self.name}"


class Skill(models.Model):
    category = models.ForeignKey(CursusCategory, on_delete=models.CASCADE, related_name='skills')
    name     = models.CharField(max_length=200)
    order    = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Compétence'
        verbose_name_plural = 'Compétences'
        ordering            = ['order', 'pk']

    def __str__(self):
        return self.name


class FormationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=Formation.Status.ACTIVE)


class Formation(models.Model):
    """Formation suivie par un groupe d'élèves (ex. « N2 promo 2026 ») : instance d'un cursus,
    indépendante des saisons."""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'En cours'
        CLOSED = 'closed', 'Terminée'

    club = models.ForeignKey(Club, on_delete=models.CASCADE, default=get_default_club, related_name='formations',
                             verbose_name='Club')
    name       = models.CharField('Nom', max_length=200)
    cursus     = models.ForeignKey(Cursus, on_delete=models.PROTECT, related_name='formations', verbose_name='Cursus')
    start_date = models.DateField('Début', null=True, blank=True)
    end_date   = models.DateField('Fin', null=True, blank=True)
    managers   = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='managed_formations',
                                        verbose_name='Responsables')
    status     = models.CharField('Statut', max_length=20, choices=Status.choices, default=Status.ACTIVE)

    objects = FormationQuerySet.as_manager()

    class Meta:
        verbose_name        = 'Formation'
        verbose_name_plural = 'Formations'
        ordering            = ['status', '-start_date', 'name']

    def __str__(self):
        return self.name


class Member(models.Model):
    """Élève. Le compte utilisateur (facultatif, rôle « élève ») donne accès à « Mon suivi » en lecture seule."""

    club = models.ForeignKey(Club, on_delete=models.CASCADE, default=get_default_club, related_name='members',
                             verbose_name='Club')
    user        = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name='student_profile', verbose_name='Compte')
    first_name  = models.CharField('Prénom', max_length=150)
    last_name   = models.CharField('Nom', max_length=150)
    birthdate   = models.DateField('Date de naissance', null=True, blank=True)
    medical_certificate_date = models.DateField('Certificat médical', null=True, blank=True)
    emergency_contact_name   = models.CharField("Contact d'urgence", max_length=200, blank=True)
    emergency_contact_phone  = models.CharField("Téléphone d'urgence", max_length=50, blank=True)

    class Meta:
        verbose_name        = 'Élève'
        verbose_name_plural = 'Élèves'
        ordering            = ['last_name', 'first_name']

    @property
    def email(self):
        return self.user.email if self.user_id else ''

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def cursus_ids(self):
        """Cursus des formations auxquelles l'élève est inscrit (hors abandons)."""
        return set(
            self.enrollments.exclude(status=Enrollment.Status.DROPPED)
            .values_list('formation__cursus_id', flat=True)
        )


class Enrollment(models.Model):
    """Inscription d'un élève à une formation."""

    class Status(models.TextChoices):
        ACTIVE    = 'active',    'En formation'
        COMPLETED = 'completed', 'Terminée'
        DROPPED   = 'dropped',   'Abandon'

    member    = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='enrollments', verbose_name='Élève')
    formation = models.ForeignKey(Formation, on_delete=models.CASCADE, related_name='enrollments', verbose_name='Formation')
    status    = models.CharField('Statut', max_length=20, choices=Status.choices, default=Status.ACTIVE)
    date      = models.DateField("Date d'inscription", default=timezone.localdate)

    class Meta:
        verbose_name        = 'Inscription'
        verbose_name_plural = 'Inscriptions'
        ordering            = ['status', '-date', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['member', 'formation'], name='unique_enrollment'),
        ]

    def __str__(self):
        return f"{self.member} — {self.formation}"


class MemberSkill(models.Model):
    class SkillStatus(models.TextChoices):
        NOT_ACQUIRED = 'not_acquired', 'Non acquis'
        IN_PROGRESS  = 'in_progress',  "En cours d'acquisition"
        ACQUIRED     = 'acquired',     'Acquis'

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='member_skills')
    skill  = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='member_skills')
    status = models.CharField(max_length=20, choices=SkillStatus.choices, default=SkillStatus.NOT_ACQUIRED)

    class Meta:
        verbose_name        = 'Compétence élève'
        verbose_name_plural = 'Compétences élèves'
        constraints = [
            models.UniqueConstraint(fields=['member', 'skill'], name='unique_member_skill')
        ]

    def __str__(self):
        return f"{self.member} — {self.skill}"


class SkillEvaluation(models.Model):
    member  = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='skill_evaluations')
    skill   = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='evaluations')
    date    = models.DateField()
    status  = models.CharField(max_length=20, choices=MemberSkill.SkillStatus.choices)
    author  = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='+', verbose_name='Évaluateur')

    class Meta:
        verbose_name        = 'Évaluation'
        verbose_name_plural = 'Évaluations'
        ordering            = ['-date']

    def __str__(self):
        return f"{self.member} — {self.skill} ({self.date})"
