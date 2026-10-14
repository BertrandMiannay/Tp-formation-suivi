from django.conf import settings
from django.db import models

from userManagement.models import Role


DEFAULT_CLUB_NAME = 'Club'


class Club(models.Model):
    """Organisation (club) : chaque saison, cursus, formation, élève et séance appartient à un club."""

    name = models.CharField('Nom', max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Club'
        verbose_name_plural = 'Clubs'
        ordering            = ['name']

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        # Formation.cursus est protégé : les formations partent avant les cursus du club.
        self.formations.all().delete()
        return super().delete(*args, **kwargs)


def get_default_club():
    """Club par défaut (le plus ancien, créé au besoin) : valeur par défaut du champ `club` tant que
    les vues ne travaillent pas encore sur un club actif."""
    club = Club.objects.order_by('pk').first()
    if club is None:
        club = Club.objects.create(name=DEFAULT_CLUB_NAME)
    return club.pk


class Membership(models.Model):
    """Rôle d'un compte dans un club (élève, encadrant ou administrateur du club). Un compte peut appartenir
    à plusieurs clubs, avec un rôle différent dans chacun ; un superutilisateur (super-admin) a accès à tous."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships',
                             verbose_name='Compte')
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name='memberships', verbose_name='Club')
    role = models.CharField('Rôle', max_length=20, choices=Role.choices)

    class Meta:
        verbose_name        = 'Membre du club'
        verbose_name_plural = 'Membres du club'
        constraints = [
            models.UniqueConstraint(fields=['user', 'club'], name='unique_membership'),
        ]

    def __str__(self):
        return f"{self.user} — {self.club} ({self.get_role_display()})"
