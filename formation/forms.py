from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from userManagement.forms import StaffChoiceField
from userManagement.models import Role
from .models import Cursus, Enrollment, Formation, Member


class AccountChoiceField(forms.ModelChoiceField):
    """Comptes sans fiche élève (encadrant qui suit une formation, élève invité depuis la page Utilisateurs…)."""

    def label_from_instance(self, user):
        name = user.get_full_name() or (user.username if user.is_active else "invitation en attente")
        parts = [name, user.email, user.role_label]
        return ' · '.join(p for p in parts if p)


class StudentForm(forms.ModelForm):
    account = AccountChoiceField(
        queryset=get_user_model().objects.none(), required=False,
        label='À partir d\'un compte existant', empty_label='— Aucun : nouvel élève —',
        help_text="La fiche est rattachée au compte choisi (prénom, nom et email repris du compte).",
    )
    email = forms.EmailField(
        label='Email', required=False,
        help_text="Facultatif : renseigné, il crée le compte élève (lien d'invitation à transmettre).",
    )
    formation = forms.ModelChoiceField(
        queryset=Formation.objects.none(), required=False, label='Inscrire à la formation',
    )

    class Meta:
        model  = Member
        fields = ['first_name', 'last_name', 'birthdate', 'medical_certificate_date',
                  'emergency_contact_name', 'emergency_contact_phone']
        widgets = {
            'birthdate': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'medical_certificate_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['email'].initial = self.instance.email
            if not self.manages_account_email:
                # Compte encadrant / administrateur rattaché : son email est géré par son titulaire.
                self.fields['email'].disabled = True
                self.fields['email'].help_text = (
                    "Compte encadrant ou administrateur : l'email ne se modifie pas depuis la fiche élève."
                )
            del self.fields['formation']  # inscriptions gérées depuis la fiche
            del self.fields['account']
        else:
            self.fields['formation'].queryset = Formation.objects.active()
            self.fields['account'].queryset = (
                get_user_model().objects.filter(student_profile__isnull=True)
                .order_by('first_name', 'last_name', 'email')
            )
            self.selected_account = self._selected_account()
            if self.selected_account:
                # L'email est celui du compte ; prénom et nom en sont repris s'ils sont renseignés.
                self.fields['email'].disabled = True
                self.fields['email'].initial = self.selected_account.email
                self.fields['email'].help_text = "Email du compte choisi."
                if not self.is_bound:
                    for field in ('first_name', 'last_name'):
                        value = getattr(self.selected_account, field)
                        if value and not self.initial.get(field):
                            self.initial[field] = value

    def _selected_account(self):
        """Compte choisi (POST, ou ?user= à l'affichage), s'il n'a pas encore de fiche."""
        pk = self.data.get('account') if self.is_bound else self.initial.get('account')
        if not str(pk or '').isdigit():
            return None
        return self.fields['account'].queryset.filter(pk=pk).first()

    @property
    def manages_account_email(self):
        """La fiche ne pilote l'email que d'un compte élève (ou d'une fiche sans compte)."""
        user = self.instance.user if self.instance.user_id else None
        return user is None or user.role == Role.STUDENT

    def clean_email(self):
        if getattr(self, 'selected_account', None):
            return self.selected_account.email
        if not self.manages_account_email:
            return self.instance.user.email
        email = self.cleaned_data['email'].strip().lower()
        if not email:
            if self.instance.user_id:
                raise forms.ValidationError("L'élève a un compte : son email ne peut pas être retiré.")
            return ''
        User = get_user_model()
        others = User.objects.filter(email__iexact=email)
        if self.instance.user_id:
            others = others.exclude(pk=self.instance.user_id)
        owner = others.filter(student_profile__isnull=False).first()
        if owner:
            raise forms.ValidationError("Cette adresse est déjà utilisée par un autre élève.")
        if self.instance.user_id and others.exists():
            raise forms.ValidationError("Cette adresse est déjà utilisée par un autre compte.")
        return email


class FormationForm(forms.ModelForm):
    managers = StaffChoiceField(label='Responsables')

    class Meta:
        model  = Formation
        fields = ['name', 'cursus', 'start_date', 'end_date', 'managers']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'end_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cursus'].queryset = Cursus.objects.filter(
            Q(status=Cursus.Status.ACTIVE) | Q(pk=self.instance.cursus_id)
        ).order_by('name')

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('start_date'), cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', "La fin doit être postérieure au début.")
        return cleaned


class QuickStudentForm(forms.Form):
    """Création rapide d'un élève (sans compte) depuis une formation ou une séance."""
    first_name = forms.CharField(label='Prénom', max_length=150)
    last_name  = forms.CharField(label='Nom', max_length=150)

    def save(self, formation=None):
        """Crée l'élève et l'inscrit à `formation` si elle est fournie."""
        with transaction.atomic():
            member = Member.objects.create(**self.cleaned_data)
            if formation:
                Enrollment.objects.create(member=member, formation=formation)
        return member
