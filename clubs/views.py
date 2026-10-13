from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from userManagement.models import Role

from .middleware import set_active_club


@login_required
def club_choose(request):
    """Choix du club actif parmi ceux du compte (GET : liste, POST : choix)."""
    clubs = request.user.clubs().order_by('name', 'pk')
    if request.method == 'POST':
        club = get_object_or_404(clubs, pk=request.POST.get('club_id'))
        set_active_club(request, club)
        messages.success(request, f"Club actif : {club}.")
        next_url = request.POST.get('next', '')
        if not url_has_allowed_host_and_scheme(next_url, {request.get_host()}, request.is_secure()):
            next_url = '/'
        return redirect(next_url)
    return render(request, 'clubs/club_choose.html', {
        'clubs': [(club, Role(request.user.role_in(club)).label if request.user.role_in(club) else '')
                  for club in clubs],
    })
