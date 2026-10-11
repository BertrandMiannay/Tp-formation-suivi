import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.functional import cached_property


class Role(models.TextChoices):
    """Les trois niveaux de compte, chacun matérialisé par un groupe Django du même nom."""
    STUDENT    = 'student',    'Élève'
    INSTRUCTOR = 'instructor', 'Encadrant'
    ADMIN      = 'admin',      'Administrateur'


STAFF_ROLES = [Role.INSTRUCTOR, Role.ADMIN]


class CustomUser(AbstractUser):
    invite_token = models.UUIDField(null=True, blank=True, unique=True)
    invite_expires_at = models.DateTimeField(null=True, blank=True)

    @cached_property
    def role(self):
        """Rôle le plus élevé de l'utilisateur (None s'il n'en a aucun)."""
        if self.is_superuser:
            return Role.ADMIN
        names = set(self.groups.values_list('name', flat=True))
        for role in (Role.ADMIN, Role.INSTRUCTOR, Role.STUDENT):
            if role in names:
                return role
        return None

    @property
    def role_label(self):
        return Role(self.role).label if self.role else ''

    @property
    def is_administrator(self):
        return self.role == Role.ADMIN

    @property
    def is_club_staff(self):
        return self.role in STAFF_ROLES
