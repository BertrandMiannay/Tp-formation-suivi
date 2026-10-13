from django.utils.functional import SimpleLazyObject

from .models import Club, get_default_club

SESSION_KEY = 'club_id'


def get_active_club(request):
    """Club sur lequel travaillent les vues : celui choisi en session s'il existe, sinon le club par défaut.
    (Le choix du club et le contrôle d'appartenance arrivent avec les rôles par club.)"""
    club_id = request.session.get(SESSION_KEY) if hasattr(request, 'session') else None
    club = Club.objects.filter(pk=club_id).first() if club_id else None
    return club or Club.objects.get(pk=get_default_club())


class ActiveClubMiddleware:
    """Expose le club actif dans `request.club` (évalué à la première utilisation)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.club = SimpleLazyObject(lambda: get_active_club(request))
        return self.get_response(request)
