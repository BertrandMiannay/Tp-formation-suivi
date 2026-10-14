from django import forms

from .models import Club


class ClubForm(forms.ModelForm):
    class Meta:
        model  = Club
        fields = ['name']


class ClubCreateForm(ClubForm):
    admin_email = forms.EmailField(
        label="Email du premier administrateur", required=False,
        help_text="Facultatif. Compte existant : il devient administrateur du club ; sinon une invitation est créée "
                  "(lien à transmettre, affiché sur la page du club).",
    )


class ClubAdminForm(forms.Form):
    email = forms.EmailField(label="Email")
