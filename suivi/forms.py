from django import forms

from formation.models import Formation, Skill
from userManagement.forms import StaffChoiceField
from .models import Exercise, StudentNote, TrainingSession


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


class ExerciseForm(forms.ModelForm):
    class Meta:
        model  = Exercise
        fields = ['date', 'name', 'skill', 'result', 'comment', 'session']
        labels = {
            'date': 'Date',
            'name': 'Exercice',
            'skill': 'Compétence liée',
            'result': 'Résultat',
            'comment': 'Commentaire',
            'session': 'Séance',
        }
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'comment': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        if member is not None:
            self.fields['skill'].queryset = (
                Skill.objects.filter(category__cursus__in=member.cursus_ids())
                .select_related('category__cursus')
                .order_by('category__cursus__name', 'category__order', 'order')
            )
            self.fields['session'].queryset = TrainingSession.objects.filter(attendances__member=member).distinct()
        self.fields['skill'].label_from_instance = lambda s: f"{s.category.cursus.name} — {s.name}"


class StudentNoteForm(forms.ModelForm):
    class Meta:
        model  = StudentNote
        fields = ['date', 'content', 'visibility', 'session']
        labels = {
            'date': 'Date',
            'content': 'Note',
            'visibility': 'Visibilité',
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
