from .models import Club

SESSION_KEY = 'club_id'


def get_active_club(request):
    """Club actif d'un compte connecté, parmi ses clubs : celui choisi dans la session, sinon le dernier
    utilisé, sinon le premier (par nom). None si le compte n'appartient à aucun club."""
    user = request.user
    if not user.is_authenticated:
        return None
    clubs = user.clubs()
    for club_id in (request.session.get(SESSION_KEY), user.last_club_id):
        if club_id:
            club = clubs.filter(pk=club_id).first()
            if club:
                return club
    return clubs.order_by('name', 'pk').first()


def set_active_club(request, club):
    """Choix du club actif (club accessible au compte, vérifié par l'appelant) : session et dernier club utilisé."""
    request.session[SESSION_KEY] = club.pk
    user = request.user
    if user.last_club_id != club.pk:
        user.last_club = club
        user.save(update_fields=['last_club'])
    user.active_club = request.club = club


class ActiveClubMiddleware:
    """Expose le club actif dans `request.club` et `request.user.active_club` (rôle du compte dans ce club)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.club = get_active_club(request)
        if request.user.is_authenticated:
            request.user.active_club = request.club
        return self.get_response(request)
