from django import forms
import re

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
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
    required_css_class = 'required'  # libellé suivi d'une étoile (app.css)
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


class StudentImportForm(forms.Form):
    required_css_class = 'required'
    """Import de plusieurs élèves : une ligne « Nom ; Prénom ; Email » par élève (email facultatif)."""
    MAX_LINES = 200

    lines = forms.CharField(
        label='Élèves', widget=forms.Textarea(attrs={'rows': 12, 'placeholder': 'Martin ; Alice ; alice@example.com\nDurand ; Bob'}),
        help_text="Une ligne par élève : nom, prénom et email (facultatif), séparés par « ; », une virgule "
                  "ou une tabulation (copier-coller depuis un tableur). Une ligne d'en-tête « Nom… » est ignorée.",
    )
    formation = forms.ModelChoiceField(
        queryset=Formation.objects.none(), required=False, label='Inscrire à la formation',
        empty_label='— Sans inscription —',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['formation'].queryset = Formation.objects.active()

    def clean_lines(self):
        """Liste de dicts {first_name, last_name, email} ; toutes les erreurs sont signalées d'un coup."""
        rows, errors, seen_emails = [], [], set()
        raw_lines = [(n, line.strip()) for n, line in enumerate(self.cleaned_data['lines'].splitlines(), start=1)]
        raw_lines = [(n, line) for n, line in raw_lines if line]
        if raw_lines and raw_lines[0][1].lower().lstrip('\ufeff').startswith('nom'):
            raw_lines = raw_lines[1:]
        if len(raw_lines) > self.MAX_LINES:
            raise forms.ValidationError(f"{self.MAX_LINES} élèves au maximum par import.")
        emails_in_use = {
            e.lower() for e in get_user_model().objects.filter(student_profile__isnull=False)
            .values_list('email', flat=True) if e
        }
        for n, line in raw_lines:
            cells = [c.strip() for c in re.split(r'[;\t,]', line)]
            while cells and not cells[-1]:
                cells.pop()
            if len(cells) not in (2, 3) or not cells[0] or not cells[1]:
                errors.append(f"Ligne {n} : nom et prénom attendus (« {line} »).")
                continue
            last_name, first_name = cells[0], cells[1]
            email = cells[2].lower() if len(cells) == 3 else ''
            if len(first_name) > 150 or len(last_name) > 150:
                errors.append(f"Ligne {n} : nom ou prénom trop long.")
                continue
            if email:
                try:
                    validate_email(email)
                except ValidationError:
                    errors.append(f"Ligne {n} : adresse email invalide (« {email} »).")
                    continue
                if email in emails_in_use:
                    errors.append(f"Ligne {n} : {email} est déjà utilisée par un autre élève.")
                    continue
                if email in seen_emails:
                    errors.append(f"Ligne {n} : {email} apparaît plusieurs fois.")
                    continue
                seen_emails.add(email)
            rows.append({'first_name': first_name, 'last_name': last_name, 'email': email})
        if errors:
            raise forms.ValidationError(errors)
        if not rows:
            raise forms.ValidationError("Aucun élève à importer.")
        return rows


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
