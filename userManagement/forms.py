from django import forms
from django.contrib.auth import get_user_model

from .models import STAFF_ROLES


def staff_users(club):
    """Équipe encadrante active du club (encadrants et administrateurs)."""
    return (
        get_user_model().objects
        .filter(is_active=True, memberships__club=club, memberships__role__in=STAFF_ROLES)
        .distinct()
        .order_by('first_name', 'last_name', 'username')
    )


class StaffChoiceField(forms.ModelMultipleChoiceField):
    """Choix multiple parmi l'équipe encadrante d'un club (queryset posé par le formulaire : `staff_users(club)`)."""

    def __init__(self, **kwargs):
        kwargs.setdefault('widget', forms.CheckboxSelectMultiple)
        super().__init__(queryset=get_user_model().objects.none(), required=False, **kwargs)

    def label_from_instance(self, obj):
        return obj.get_full_name() or obj.username
