from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.functional import cached_property


class Role(models.TextChoices):
    """Les trois rôles d'un compte dans un club (`clubs.Membership`)."""
    STUDENT    = 'student',    'Élève'
    INSTRUCTOR = 'instructor', 'Encadrant'
    ADMIN      = 'admin',      'Administrateur'


STAFF_ROLES = [Role.INSTRUCTOR, Role.ADMIN]


class CustomUser(AbstractUser):
    invite_token = models.UUIDField(null=True, blank=True, unique=True)
    invite_expires_at = models.DateTimeField(null=True, blank=True)
    last_club = models.ForeignKey('clubs.Club', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
                                  verbose_name='Dernier club utilisé')

    # Club actif de la requête, posé par `clubs.middleware.ActiveClubMiddleware` : `role` et les
    # indicateurs qui en dépendent s'entendent dans ce club.
    active_club = None

    @cached_property
    def _club_roles(self):
        return dict(self.memberships.values_list('club_id', 'role'))

    def role_in(self, club):
        """Rôle dans `club` (None s'il n'en est pas membre) ; un superutilisateur est administrateur partout."""
        if club is None:
            return None
        if self.is_superuser:
            return Role.ADMIN
        return self._club_roles.get(club.pk)

    def clubs(self):
        """Clubs accessibles : tous pour un superutilisateur (super-admin), sinon ceux dont il est membre."""
        from clubs.models import Club
        return Club.objects.all() if self.is_superuser else Club.objects.filter(memberships__user=self)

    def only_in_club(self, club):
        """Compte membre de `club` seulement (aucun autre club, pas superutilisateur) : un club ne gère
        (email, mot de passe, invitation, suppression) que les comptes qui ne servent nulle part ailleurs."""
        return not self.is_superuser and set(self._club_roles) == {club.pk}

    @property
    def role(self):
        """Rôle dans le club actif."""
        return self.role_in(self.active_club)

    @property
    def role_label(self):
        return Role(self.role).label if self.role else ''

    @property
    def is_administrator(self):
        return self.role == Role.ADMIN

    @property
    def is_club_staff(self):
        return self.role in STAFF_ROLES

    @cached_property
    def student_profile(self):
        """Fiche élève du compte dans le club actif (None s'il n'en a pas)."""
        if self.active_club is None:
            return None
        return self.student_profiles.filter(club=self.active_club).first()
