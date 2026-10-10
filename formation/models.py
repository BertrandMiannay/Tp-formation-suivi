from django.conf import settings
from django.db import models


class Season(models.Model):
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

    name   = models.CharField(max_length=200)
    date   = models.DateField(help_text="Date de version du cursus")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        verbose_name        = 'Cursus'
        verbose_name_plural = 'Cursus'
        ordering            = ['-date']

    def __str__(self):
        return self.name


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


class Member(models.Model):
    """Élève. Son compte utilisateur (rôle « membre ») lui donne accès à « Mon suivi »."""

    user        = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name='student_profile', verbose_name='Compte')
    first_name  = models.CharField('Prénom', max_length=150)
    last_name   = models.CharField('Nom', max_length=150)
    birthdate   = models.DateField('Date de naissance', null=True, blank=True)
    medical_certificate_date = models.DateField('Certificat médical', null=True, blank=True)
    emergency_contact_name   = models.CharField("Contact d'urgence", max_length=200, blank=True)
    emergency_contact_phone  = models.CharField("Téléphone d'urgence", max_length=50, blank=True)
    formations  = models.ManyToManyField(Cursus, blank=True, related_name='members', verbose_name='Niveaux préparés')
    seasons     = models.ManyToManyField(Season, blank=True, related_name='members', verbose_name='Saisons')

    class Meta:
        verbose_name        = 'Élève'
        verbose_name_plural = 'Élèves'
        ordering            = ['last_name', 'first_name']

    @property
    def email(self):
        return self.user.email if self.user_id else ''

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


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
    comment = models.TextField(blank=True)
    author  = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='+', verbose_name='Évaluateur')

    class Meta:
        verbose_name        = 'Évaluation'
        verbose_name_plural = 'Évaluations'
        ordering            = ['-date']

    def __str__(self):
        return f"{self.member} — {self.skill} ({self.date})"
