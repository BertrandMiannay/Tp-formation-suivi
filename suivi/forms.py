from django import forms

from formation.models import Formation, Skill
from userManagement.forms import StaffChoiceField
from .models import Comment, TrainingSession


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


def add_comments(*, member, date, author, content='', staff_content='', session=None, skill=None):
    """Crée les commentaires saisis dans un champ `_comment_fields.html` : la partie visible par l'élève
    et la note équipe deviennent chacune un commentaire. Renvoie les commentaires créés."""
    created = []
    for text, staff_only in ((content, False), (staff_content, True)):
        text = (text or '').strip()
        if text:
            created.append(Comment.objects.create(
                member=member, session=session, skill=skill, date=date,
                content=text, staff_only=staff_only, author=author,
            ))
    return created


class CommentForm(forms.Form):
    """Ajout d'un commentaire depuis la fiche élève : séance et compétence facultatives."""

    date          = forms.DateField(label='Date', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    session       = forms.ModelChoiceField(TrainingSession.objects.none(), label='Séance', required=False)
    skill         = forms.ModelChoiceField(Skill.objects.none(), label='Compétence', required=False)
    content       = forms.CharField(required=False)
    staff_content = forms.CharField(required=False)

    def __init__(self, *args, member, **kwargs):
        super().__init__(*args, **kwargs)
        self.member = member
        self.fields['session'].queryset = (
            TrainingSession.objects.filter(attendances__member=member).distinct().order_by('-date', '-pk')
        )
        self.fields['skill'].queryset = (
            Skill.objects.filter(category__cursus__in=member.cursus_ids()).select_related('category__cursus')
            .order_by('category__cursus__name', 'category__order', 'category__pk', 'order', 'pk')
        )
        self.fields['skill'].label_from_instance = lambda s: f"{s.category.cursus.name} — {s.name}"

    def clean(self):
        cleaned = super().clean()
        cleaned['content'] = (cleaned.get('content') or '').strip()
        cleaned['staff_content'] = (cleaned.get('staff_content') or '').strip()
        if not cleaned['content'] and not cleaned['staff_content']:
            raise forms.ValidationError("Le commentaire est vide.")
        return cleaned

    def save(self, author):
        data = self.cleaned_data
        return add_comments(
            member=self.member, date=data['date'], author=author, session=data['session'], skill=data['skill'],
            content=data['content'], staff_content=data['staff_content'],
        )
