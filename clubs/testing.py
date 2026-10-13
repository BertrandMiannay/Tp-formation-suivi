"""Outils pour les tests : rôle d'un compte dans un club."""
from .models import Club, Membership


def default_club():
    return Club.objects.order_by('pk').first()


def add_role(user, role, club=None):
    """Donne à `user` le rôle `role` dans `club` (le club par défaut si omis)."""
    Membership.objects.update_or_create(user=user, club=club or default_club(), defaults={'role': role})
    return user
