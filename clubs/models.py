from django.db import models


DEFAULT_CLUB_NAME = 'Club'


class Club(models.Model):
    """Organisation (club) : chaque saison, cursus, formation, élève et séance appartient à un club."""

    name = models.CharField('Nom', max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Club'
        verbose_name_plural = 'Clubs'
        ordering            = ['name']

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        # Formation.cursus est protégé : les formations partent avant les cursus du club.
        self.formations.all().delete()
        return super().delete(*args, **kwargs)


def get_default_club():
    """Club par défaut (le plus ancien, créé au besoin) : valeur par défaut du champ `club` tant que
    les vues ne travaillent pas encore sur un club actif."""
    club = Club.objects.order_by('pk').first()
    if club is None:
        club = Club.objects.create(name=DEFAULT_CLUB_NAME)
    return club.pk
