import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from formation.models import Enrollment
from userManagement.models import STAFF_ROLES, Role
from userManagement.views import create_invited_user, invite_url_for, superadmin_required

from .forms import ClubAdminForm, ClubCreateForm, ClubForm
from .middleware import set_active_club
from .models import Club, Membership

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Gestion des clubs (super-admin)
# ---------------------------------------------------------------------------

def add_club_admin(club, email):
    """Nomme administrateur du club le compte de cet email (rôle relevé s'il était déjà membre), ou crée une
    invitation administrateur. Renvoie le compte."""
    user = get_user_model().objects.filter(email__iexact=email).order_by('-is_active', 'pk').first()
    if user is None:
        return create_invited_user(email.lower(), club=club, role=Role.ADMIN)
    Membership.objects.update_or_create(user=user, club=club, defaults={'role': Role.ADMIN})
    return user


def _active_students(club):
    return Enrollment.objects.filter(formation__club=club, status=Enrollment.Status.ACTIVE).values('member').distinct().count()


@superadmin_required
def club_list(request):
    clubs = Club.objects.annotate(
        member_count=Count('members', distinct=True),
        staff_count=Count('memberships', filter=Q(memberships__role__in=STAFF_ROLES), distinct=True),
        formation_count=Count('formations', filter=Q(formations__status='active'), distinct=True),
    ).order_by('name')
    return render(request, 'clubs/club_list.html', {'clubs': clubs, 'active_tab': 'clubs'})


@superadmin_required
def club_create(request):
    form = ClubCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            club = form.save()
            email = form.cleaned_data['admin_email']
            admin = add_club_admin(club, email) if email else None
        logger.info("CLUB_CREATE pk=%s name=%s admin=%s by=%s",
                    club.pk, club.name, admin.pk if admin else None, request.user.username)
        messages.success(request, f"Club « {club} » créé." + (
            " Transmettez le lien d'invitation à son administrateur." if admin and not admin.is_active else ""
        ))
        return redirect('club-detail', pk=club.pk)
    return render(request, 'clubs/club_form.html', {'form': form, 'active_tab': 'clubs'})


@superadmin_required
def club_detail(request, pk):
    club = get_object_or_404(Club, pk=pk)
    rename_form = ClubForm(instance=club)
    admin_form = ClubAdminForm()

    if request.method == 'POST':
        action = request.POST.get('_action')
        if action == 'rename':
            rename_form = ClubForm(request.POST, instance=club)
            if rename_form.is_valid():
                rename_form.save()
                logger.info("CLUB_RENAME pk=%s name=%s by=%s", club.pk, club.name, request.user.username)
                messages.success(request, "Club renommé.")
                return redirect('club-detail', pk=pk)
        elif action == 'add_admin':
            admin_form = ClubAdminForm(request.POST)
            if admin_form.is_valid():
                admin = add_club_admin(club, admin_form.cleaned_data['email'])
                logger.info("CLUB_ADMIN_ADD club=%s user=%s by=%s", club.pk, admin.pk, request.user.username)
                messages.success(request, f"{admin.email} est administrateur du club.")
                return redirect('club-detail', pk=pk)
        elif action == 'remove_admin':
            membership = get_object_or_404(Membership, pk=request.POST.get('membership_pk'), club=club, role=Role.ADMIN)
            user = membership.user
            with transaction.atomic():
                membership.delete()
                # Invitation jamais acceptée et sans autre club : le compte ne sert plus à rien.
                if not user.is_active and not user.is_superuser and not user.memberships.exists():
                    user.delete()
            logger.info("CLUB_ADMIN_REMOVE club=%s user=%s by=%s", club.pk, user.pk, request.user.username)
            messages.success(request, f"{user.email or user.username} n'est plus administrateur du club.")
            return redirect('club-detail', pk=pk)

    admins = [
        {'membership': m, 'user': m.user, 'invite_url': invite_url_for(request, m.user) if not m.user.is_active else None}
        for m in club.memberships.filter(role=Role.ADMIN).select_related('user').order_by('user__username')
    ]
    return render(request, 'clubs/club_detail.html', {
        'club': club,
        'rename_form': rename_form,
        'admin_form': admin_form,
        'admins': admins,
        'counts': {
            'members': club.members.count(),
            'active_students': _active_students(club),
            'formations': club.formations.count(),
            'sessions': club.training_sessions.count(),
            'memberships': club.memberships.count(),
        },
        'deletable': _deletion_blocker(club) is None,
        'deletion_blocker': _deletion_blocker(club),
        'active_tab': 'clubs',
    })


def _deletion_blocker(club):
    """Raison qui empêche de supprimer le club, ou None."""
    if Club.objects.count() <= 1:
        return "C'est le seul club : créez-en un autre avant de le supprimer."
    if _active_students(club):
        return "Des élèves sont en formation dans ce club : clôturez ou retirez leurs inscriptions d'abord."
    return None


@superadmin_required
def club_delete(request, pk):
    """Suppression définitive d'un club et de toutes ses données, confirmée en retapant son nom."""
    club = get_object_or_404(Club, pk=pk)
    if request.method != 'POST':
        return redirect('club-detail', pk=pk)
    blocker = _deletion_blocker(club)
    if blocker:
        messages.error(request, blocker)
    elif request.POST.get('confirm_name', '').strip() != club.name:
        messages.error(request, "Le nom saisi ne correspond pas : le club n'a pas été supprimé.")
    else:
        name = club.name
        with transaction.atomic():
            club.delete()
        logger.info("CLUB_DELETE pk=%s name=%s by=%s", pk, name, request.user.username)
        messages.success(request, f"Club « {name} » et toutes ses données supprimés.")
        return redirect('club-list')
    return redirect(reverse('club-detail', args=[pk]) + '#supprimer')
