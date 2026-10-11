from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from userManagement.forms import StaffChoiceField
from .models import Cursus, Enrollment, Formation, Member


class StudentForm(forms.ModelForm):
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
            del self.fields['formation']  # inscriptions gérées depuis la fiche
        else:
            self.fields['formation'].queryset = Formation.objects.active()

    def clean_email(self):
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
