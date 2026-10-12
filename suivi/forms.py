from django import forms

from formation.models import Formation, Skill
from userManagement.forms import StaffChoiceField
from .models import StudentNote, TrainingSession


class TrainingSessionForm(forms.ModelForm):
    instructors = StaffChoiceField(label='Encadrants')

    class Meta:
        model  = TrainingSession
        fields = ['date', 'title', 'location', 'formations', 'instructors', 'notes']
        labels = {
            'date': 'Date',
            'title': 'Thème',
            'location': 'Lieu',
            'formations': 'Formations',
            'notes': 'Déroulé / remarques (équipe encadrante)',
        }
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'formations': forms.CheckboxSelectMultiple,
            'notes': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        formation_qs = Formation.objects.active()
        if self.instance.pk:
            formation_qs = formation_qs | self.instance.formations.all()
        self.fields['formations'].queryset = formation_qs.distinct().order_by('name')


class StudentNoteForm(forms.ModelForm):
    class Meta:
        model  = StudentNote
        fields = ['date', 'content', 'staff_content', 'session']
        labels = {
            'date': 'Date',
            'session': 'Séance',
        }
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'content': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        if member is not None:
            self.fields['session'].queryset = TrainingSession.objects.filter(attendances__member=member).distinct()

    def clean(self):
        cleaned = super().clean()
        cleaned['content'] = (cleaned.get('content') or '').strip()
        cleaned['staff_content'] = (cleaned.get('staff_content') or '').strip()
        if not cleaned['content'] and not cleaned['staff_content']:
            raise forms.ValidationError("La note est vide.")
        return cleaned
