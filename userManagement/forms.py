from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import STAFF_ROLES


def staff_users():
    return (
        get_user_model().objects
        .filter(is_active=True)
        .filter(Q(is_superuser=True) | Q(groups__name__in=STAFF_ROLES))
        .distinct()
        .order_by('first_name', 'last_name', 'username')
    )


class StaffChoiceField(forms.ModelMultipleChoiceField):
    """Choix multiple parmi l'équipe encadrante (encadrants et administrateurs actifs)."""

    def __init__(self, **kwargs):
        kwargs.setdefault('widget', forms.CheckboxSelectMultiple)
        super().__init__(queryset=staff_users(), required=False, **kwargs)

    def label_from_instance(self, obj):
        return obj.get_full_name() or obj.username
