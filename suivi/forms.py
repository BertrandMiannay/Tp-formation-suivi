from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from formation.models import Formation, Skill
from userManagement.models import STAFF_ROLES
from .models import Exercise, StudentNote, TrainingSession


def staff_users():
    return (
        get_user_model().objects
        .filter(is_active=True)
        .filter(Q(is_superuser=True) | Q(groups__name__in=STAFF_ROLES))
        .distinct()
        .order_by('first_name', 'last_name', 'username')
    )


class StaffChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return obj.get_full_name() or obj.username


class TrainingSessionForm(forms.ModelForm):
    instructors = StaffChoiceField(
        queryset=None, required=False, widget=forms.CheckboxSelectMultiple, label='Encadrants',
    )

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
        formation_qs = Formation.objects.filter(status=Formation.Status.ACTIVE)
        if self.instance.pk:
            formation_qs = formation_qs | self.instance.formations.all()
        self.fields['formations'].queryset = formation_qs.distinct().order_by('name')
        self.fields['instructors'].queryset = staff_users()


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
