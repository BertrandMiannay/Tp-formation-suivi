import logging
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from formation.models import Enrollment, Formation, Member, MemberSkill, Season, Skill, SkillEvaluation
from formation.forms import QuickStudentForm
from userManagement.views import can_reset_password, club_staff_required, invite_url_for
from .forms import CommentForm, TrainingSessionForm, add_comments
from .models import Attendance, Comment, TrainingSession, WorkedSkill

logger = logging.getLogger(__name__)


def _current_season():
    return Season.objects.filter(current=True).first()


def _students(formation_id=None):
    """Élèves en formation : inscrits (statut « en formation ») à une formation en cours,
    ou à la formation demandée."""
    enrollments = Enrollment.objects.filter(status=Enrollment.Status.ACTIVE)
    if formation_id:
        enrollments = enrollments.filter(formation=formation_id)
    else:
        enrollments = enrollments.filter(formation__status=Formation.Status.ACTIVE)
    return (
        Member.objects.filter(pk__in=enrollments.values('member_id'))
        .order_by('last_name', 'first_name')
    )


def _formation_filter(request):
    """Filtre ?formation= des listes : (formations proposées, id choisi ou None)."""
    formation_list = Formation.objects.active().order_by('name')
    value = request.GET.get('formation', '')
    return formation_list, int(value) if value.isdigit() else None


def _attendance_stats(attendances):
    stats = {'present': 0, 'absent': 0}
    for a in attendances:
        stats[a.status] = stats.get(a.status, 0) + 1
    stats['total'] = stats['present'] + stats['absent']
    stats['rate'] = round(100 * stats['present'] / stats['total']) if stats['total'] else None
    return stats


def _member_comments(member, for_student=False):
    comments = Comment.objects.filter(member=member)
    return comments.visible_to_student() if for_student else comments


def _skills_progress(member, for_student=False):
    """Structure formation → catégories → compétences du cursus, avec statut, nb de séances où
    l'élève a travaillé la compétence, dernière évaluation et commentaires sur la compétence (avec ou
    sans séance, plus récents d'abord ; `for_student` : sans les notes équipe). Le statut d'une
    compétence est propre à l'élève : un cursus suivi dans plusieurs formations n'est affiché
    qu'une fois (la plus récente)."""
    by_cursus = {}
    for enrollment in (
        member.enrollments.select_related('formation__cursus')
        .prefetch_related('formation__cursus__categories__skills')
    ):
        by_cursus.setdefault(enrollment.formation.cursus_id, enrollment)
    formations = list(by_cursus.values())
    skill_ids = [
        s.pk for e in formations for c in e.formation.cursus.categories.all() for s in c.skills.all()
    ]
    status_map = {
        ms.skill_id: ms.status
        for ms in MemberSkill.objects.filter(member=member, skill_id__in=skill_ids)
    }
    worked_map = {
        row['skill_id']: row['n']
        for row in (
            WorkedSkill.objects.filter(member=member, skill_id__in=skill_ids)
            .values('skill_id').annotate(n=Count('session_id', distinct=True))
        )
    }
    skill_comments = {}
    for c in _member_comments(member, for_student).filter(skill_id__in=skill_ids).select_related('session', 'author'):
        skill_comments.setdefault(c.skill_id, []).append(c)
    last_eval = {}
    for ev in SkillEvaluation.objects.filter(member=member, skill_id__in=skill_ids).select_related('author').order_by('-date', '-pk'):
        last_eval.setdefault(ev.skill_id, ev)

    result = []
    for enrollment in formations:
        formation, cursus = enrollment.formation, enrollment.formation.cursus
        categories = []
        counts = {'acquired': 0, 'in_progress': 0, 'not_acquired': 0, 'worked': 0, 'total': 0}
        for category in cursus.categories.all():
            skills = []
            for s in category.skills.all():
                status = status_map.get(s.pk, MemberSkill.SkillStatus.NOT_ACQUIRED)
                worked = worked_map.get(s.pk, 0)
                counts[status] += 1
                counts['total'] += 1
                if worked or status != MemberSkill.SkillStatus.NOT_ACQUIRED:
                    counts['worked'] += 1
                skills.append({
                    'pk': s.pk,
                    'name': s.name,
                    'status': status,
                    'status_display': MemberSkill.SkillStatus(status).label,
                    'worked': worked,
                    'last_eval': last_eval.get(s.pk),
                    'comments': skill_comments.get(s.pk, []),
                })
            categories.append({'name': category.name, 'skills': skills})
        counts['acquired_pct'] = round(100 * counts['acquired'] / counts['total']) if counts['total'] else 0
        evals = [s['last_eval'] for c in categories for s in c['skills'] if s['last_eval']]
        result.append({
            'pk': cursus.pk, 'name': formation.name, 'cursus_name': cursus.name,
            'enrollment': enrollment, 'categories': categories, 'counts': counts,
            'last_eval_date': max((ev.date for ev in evals), default=None),
        })
    return result


def _session_cursus_ids(session):
    return set(session.formations.values_list('cursus_id', flat=True))


def _candidate_cursus_ids(member_cursus_ids, session_cursus_ids):
    """Cursus proposés pour un élève lors d'une séance : ceux de ses formations, restreints aux
    cursus des formations de la séance quand ils recoupent les siens."""
    return (member_cursus_ids & session_cursus_ids) or member_cursus_ids


def _skills_of_cursus(cursus_ids):
    return list(
        Skill.objects.filter(category__cursus__in=cursus_ids)
        .select_related('category__cursus')
        .order_by('category__cursus__name', 'category__order', 'category__pk', 'order', 'pk')
    )


def _candidate_skills(session_ids, member):
    """Compétences proposables pour un élève lors d'une séance (voir `_candidate_cursus_ids`)."""
    return _skills_of_cursus(_candidate_cursus_ids(member.cursus_ids(), session_ids))


def _skill_tree(skills, worked, global_status, comments):
    """Regroupe les compétences par cursus puis catégorie, avec l'état travaillé / évalué
    pour la séance, ses commentaires de séance (`comments` : skill_id → liste) et le statut global
    de l'élève (`global_status` : skill_id → statut)."""
    tree = []
    for skill in skills:
        cursus, category = skill.category.cursus, skill.category
        if not tree or tree[-1]['pk'] != cursus.pk:
            tree.append({'pk': cursus.pk, 'name': cursus.name, 'categories': []})
        cats = tree[-1]['categories']
        if not cats or cats[-1]['pk'] != category.pk:
            cats.append({'pk': category.pk, 'name': category.name, 'skills': []})
        ws = worked.get(skill.pk)
        status = global_status.get(skill.pk, MemberSkill.SkillStatus.NOT_ACQUIRED)
        cats[-1]['skills'].append({
            'pk': skill.pk,
            'name': skill.name,
            'worked': ws is not None,
            'session_status': ws.status if ws else '',
            'comments': comments.get(skill.pk, []),
            'author': ws.author if ws else None,
            'global_status': status,
            'global_status_display': MemberSkill.SkillStatus(status).label,
        })
    return tree


def _attach_worked_skills(member, attendances, for_student=False):
    """Ajoute à chaque présence ses commentaires de séance hors compétence (`comments`) et la liste
    des compétences travaillées par l'élève ce jour-là (`worked`, chacune avec ses `comments`)."""
    session_ids = [a.session_id for a in attendances]
    comments = {}
    for c in _member_comments(member, for_student).filter(session_id__in=session_ids).select_related('author'):
        comments.setdefault((c.session_id, c.skill_id), []).append(c)
    by_session = {}
    for ws in (
        WorkedSkill.objects.filter(member=member, session_id__in=session_ids)
        .select_related('skill').order_by('skill__category__order', 'skill__order')
    ):
        ws.comments = comments.get((ws.session_id, ws.skill_id), [])
        by_session.setdefault(ws.session_id, []).append(ws)
    for a in attendances:
        a.comments = comments.get((a.session_id, None), [])
        a.worked = by_session.get(a.session_id, [])
    return attendances


def _tracking_sheet(member, season, for_student=False):
    """Partie commune de la fiche élève (staff) et de « Mon suivi » : présences de la saison avec
    les compétences travaillées, statistiques et progression par cursus.
    `for_student` : les notes équipe sont écartées."""
    attendances = member.attendances.select_related('session')
    if season:
        attendances = attendances.filter(session__season=season)
    attendances = _attach_worked_skills(
        member, list(attendances.order_by('-session__date', '-session__pk')), for_student,
    )
    formations = _skills_progress(member, for_student)
    return {
        'attendances': attendances,
        'stats': _attendance_stats(attendances),
        'formations': formations,
    }


# ---------------------------------------------------------------------------
# Séances
# ---------------------------------------------------------------------------

@club_staff_required
def session_list(request):
    seasons = Season.objects.order_by('-current', 'label')
    season_id = request.GET.get('season')
    season = Season.objects.filter(pk=season_id).first() if season_id else _current_season()
    sessions = TrainingSession.objects.all()
    if season:
        sessions = sessions.filter(season=season)
    sessions = sessions.prefetch_related('formations', 'instructors').annotate(
        present_count=Count('attendances', filter=Q(attendances__status=Attendance.Status.PRESENT), distinct=True),
        absent_count=Count('attendances', filter=~Q(attendances__status=Attendance.Status.PRESENT), distinct=True),
        skill_count=Count('worked_skills__skill', distinct=True),
    )
    return render(request, 'suivi/session_list.html', {
        'sessions': sessions,
        'seasons': seasons,
        'season': season,
        'active_tab': 'seances',
    })


@club_staff_required
def session_create(request):
    if request.method == 'POST':
        form = TrainingSessionForm(request.POST)
        if form.is_valid():
            session = form.save(commit=False)
            session.season = _current_season()
            session.save()
            form.save_m2m()
            logger.info("SESSION_CREATE pk=%s date=%s by=%s", session.pk, session.date, request.user.username)
            messages.success(request, f"{session} créée.")
            return redirect('suivi-session-detail', pk=session.pk)
    else:
        form = TrainingSessionForm(initial={'date': timezone.localdate(), 'instructors': [request.user.pk]})
    return render(request, 'suivi/session_form.html', {
        'form': form,
        'active_tab': 'seances',
    })


@club_staff_required
def session_detail(request, pk):
    session = get_object_or_404(TrainingSession, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('_action')

        if action == 'edit':
            form = TrainingSessionForm(request.POST, instance=session)
            if form.is_valid():
                form.save()
                messages.success(request, "Séance mise à jour.")
            else:
                messages.error(request, "Formulaire invalide : " + "; ".join(
                    f"{form.fields[f].label if f in form.fields else f} : {', '.join(e)}" for f, e in form.errors.items()
                ))
            return redirect('suivi-session-detail', pk=pk)

        elif action == 'attendance':
            valid = set(Attendance.Status.values)
            with transaction.atomic():
                for member in session.roster():
                    status = request.POST.get(f'att_{member.pk}', '')
                    if status in valid:
                        Attendance.objects.update_or_create(
                            session=session, member=member, defaults={'status': status},
                        )
                    else:
                        Attendance.objects.filter(session=session, member=member).delete()
                    add_comments(
                        member=member, session=session, date=session.date, author=request.user,
                        content=request.POST.get(f'att_{member.pk}_comment', ''),
                        staff_content=request.POST.get(f'att_{member.pk}_staff_comment', ''),
                    )
            messages.success(request, "Présences enregistrées.")
            return redirect(reverse('suivi-session-detail', args=[pk]) + '#presences')

        elif action == 'add_member':
            member = get_object_or_404(Member, pk=request.POST.get('member_id'))
            Attendance.objects.get_or_create(
                session=session, member=member, defaults={'status': Attendance.Status.PRESENT},
            )
            return redirect(reverse('suivi-session-detail', args=[pk]) + '#presences')

        elif action == 'create_student':
            # Nouvel élève (sans compte) présent à la séance, inscrit à l'une de ses formations.
            quick_form = QuickStudentForm(request.POST)
            formation = session.formations.filter(pk=request.POST.get('formation_id')).first()
            if quick_form.is_valid():
                with transaction.atomic():
                    member = quick_form.save(formation=formation)
                    Attendance.objects.create(session=session, member=member, status=Attendance.Status.PRESENT)
                logger.info("STUDENT_CREATE pk=%s session=%s by=%s", member.pk, session.pk, request.user.username)
                messages.success(request, f"Élève {member} créé et noté présent.")
            else:
                messages.error(request, "Prénom et nom sont obligatoires.")
            return redirect(reverse('suivi-session-detail', args=[pk]) + '#presences')

        elif action == 'worked_skills':
            member = get_object_or_404(Member, pk=request.POST.get('member_id'))
            valid = set(MemberSkill.SkillStatus.values)
            candidates = _candidate_skills(_session_cursus_ids(session), member)
            existing = {ws.skill_id: ws for ws in WorkedSkill.objects.filter(session=session, member=member)}
            current = {
                ms.skill_id: ms.status
                for ms in MemberSkill.objects.filter(member=member, skill__in=candidates)
            }
            evaluated = 0
            with transaction.atomic():
                for skill in candidates:
                    prefix = f'ws_{skill.pk}'
                    status = request.POST.get(f'{prefix}_status', '')
                    if status not in valid:
                        status = ''
                    # Un commentaire saisi sur une compétence la marque comme travaillée.
                    commented = add_comments(
                        member=member, session=session, skill=skill, date=session.date, author=request.user,
                        content=request.POST.get(f'{prefix}_comment', ''),
                        staff_content=request.POST.get(f'{prefix}_staff_comment', ''),
                    )
                    worked = bool(request.POST.get(prefix)) or bool(status) or bool(commented)
                    if not worked:
                        if skill.pk in existing:
                            existing[skill.pk].delete()
                        continue
                    ws = existing.get(skill.pk)
                    if ws and ws.status == status:
                        continue
                    WorkedSkill.objects.update_or_create(
                        session=session, member=member, skill=skill,
                        defaults={'status': status, 'author': request.user},
                    )
                    if status and status != current.get(skill.pk, MemberSkill.SkillStatus.NOT_ACQUIRED):
                        MemberSkill.objects.update_or_create(
                            member=member, skill=skill, defaults={'status': status},
                        )
                        SkillEvaluation.objects.create(
                            member=member, skill=skill, date=session.date, status=status, author=request.user,
                        )
                        evaluated += 1
            messages.success(
                request,
                f"Compétences de {member.first_name} {member.last_name} enregistrées"
                + (f" ({evaluated} évaluation(s))." if evaluated else "."),
            )
            return redirect(reverse('suivi-session-detail', args=[pk]) + f'#eleve-{member.pk}')

    roster = list(session.roster())
    attendance_map = {a.member_id: a for a in session.attendances.all()}
    comments = {}
    for c in session.comments.select_related('author'):
        comments.setdefault((c.member_id, c.skill_id), []).append(c)
    roster_rows = [
        {'member': m, 'attendance': attendance_map.get(m.pk), 'comments': comments.get((m.pk, None), [])}
        for m in roster
    ]
    stats = _attendance_stats(attendance_map.values())

    session_formations = list(session.formations.all())
    session_cursus_ids = {f.cursus_id for f in session_formations}
    worked_by_member = {}
    for ws in session.worked_skills.select_related('author'):
        worked_by_member.setdefault(ws.member_id, {})[ws.skill_id] = ws
    skill_members = []
    for r in roster_rows:
        is_present = bool(r['attendance'] and r['attendance'].status == Attendance.Status.PRESENT)
        if is_present or r['member'].pk in worked_by_member:
            skill_members.append((r['member'], is_present))

    # Compétences et statuts de tous les élèves concernés en quelques requêtes (pas une série par élève).
    member_ids = [m.pk for m, _ in skill_members]
    member_cursus = {pk: set() for pk in member_ids}
    for member_id, cursus_id in (
        Enrollment.objects.filter(member__in=member_ids).exclude(status=Enrollment.Status.DROPPED)
        .values_list('member_id', 'formation__cursus_id')
    ):
        member_cursus[member_id].add(cursus_id)
    candidate_cursus = {pk: _candidate_cursus_ids(ids, session_cursus_ids) for pk, ids in member_cursus.items()}
    all_skills = _skills_of_cursus(set().union(*candidate_cursus.values()))
    global_status = {}
    for ms in MemberSkill.objects.filter(member__in=member_ids, skill__in=all_skills):
        global_status.setdefault(ms.member_id, {})[ms.skill_id] = ms.status

    skill_rows = []
    for m, is_present in skill_members:
        worked = worked_by_member.get(m.pk, {})
        skills = [s for s in all_skills if s.category.cursus_id in candidate_cursus[m.pk]]
        skill_rows.append({
            'member': m,
            'next': reverse('suivi-session-detail', args=[pk]) + f'#eleve-{m.pk}',
            'present': is_present,
            'worked_count': len(worked),
            'acquired_count': sum(1 for ws in worked.values() if ws.status == MemberSkill.SkillStatus.ACQUIRED),
            'cursus': _skill_tree(skills, worked, global_status.get(m.pk, {}), {
                skill_id: c for (member_id, skill_id), c in comments.items() if member_id == m.pk
            }),
        })

    roster_ids = [m.pk for m in roster]
    addable_members = Member.objects.exclude(pk__in=roster_ids).order_by('last_name', 'first_name')

    return render(request, 'suivi/session_detail.html', {
        'session': session,
        'form': TrainingSessionForm(instance=session),
        'roster_rows': roster_rows,
        'stats': stats,
        'attendance_choices': Attendance.Status.choices,
        'skill_rows': skill_rows,
        'status_choices': MemberSkill.SkillStatus.choices,
        'addable_members': addable_members,
        'session_formations': session_formations,
        'active_tab': 'seances',
    })


@club_staff_required
def session_delete(request, pk):
    if request.method == 'POST':
        session = get_object_or_404(TrainingSession, pk=pk)
        logger.info("SESSION_DELETE pk=%s date=%s by=%s", session.pk, session.date, request.user.username)
        messages.success(request, f"{session} supprimée.")
        session.delete()
    return redirect('suivi-sessions')


# ---------------------------------------------------------------------------
# Élèves (liste et tableau des présences)
# ---------------------------------------------------------------------------

def attendance_matrix(sessions, students):
    """Tableau des présences : une ligne par élève, une cellule {session, att (Attendance ou None),
    comments (commentaires de séance hors compétence)} par séance."""
    att_map = {
        (a.member_id, a.session_id): a
        for a in Attendance.objects.filter(session__in=sessions, member__in=students)
    }
    comments = {}
    for c in Comment.objects.filter(session__in=sessions, member__in=students, skill=None).order_by('pk'):
        comments.setdefault((c.member_id, c.session_id), []).append(c)
    rows = []
    for m in students:
        cells = [
            {'session': s, 'att': att_map.get((m.pk, s.pk)), 'comments': comments.get((m.pk, s.pk), [])}
            for s in sessions
        ]
        rows.append({'member': m, 'cells': cells, 'stats': _attendance_stats([c['att'] for c in cells if c['att']])})
    return rows


@club_staff_required
def attendance_overview(request):
    """Ancienne page « Présences », désormais une vue de la liste des élèves."""
    params = {'vue': 'presences'}
    if request.GET.get('formation'):
        params['formation'] = request.GET['formation']
    return redirect(reverse('suivi-students') + '?' + urlencode(params))


def _attendance_context(season, formation_id):
    sessions = TrainingSession.objects.filter(season=season).order_by('date', 'pk')
    if formation_id:
        sessions = list(sessions.filter(formations=formation_id))
        students = _students(formation_id)
    else:
        sessions = list(sessions)
        # Élèves en formation, plus ceux venus à une séance de la saison sans y être inscrits.
        attended = Attendance.objects.filter(session__in=sessions).values('member_id')
        students = Member.objects.filter(Q(pk__in=_students()) | Q(pk__in=attended))
    students = list(students.order_by('last_name', 'first_name'))
    return {'sessions': sessions, 'rows': attendance_matrix(sessions, students)}


@club_staff_required
def student_list(request):
    season = _current_season()
    formation_list, formation_id = _formation_filter(request)
    show_all = request.GET.get('formation') == 'all'
    context = {
        'season': season,
        'formation_list': formation_list,
        'formation_id': formation_id,
        'show_all': show_all,
        'view': 'presences' if request.GET.get('vue') == 'presences' else 'liste',
        'active_tab': 'eleves',
    }
    if context['view'] == 'presences':
        context.update(_attendance_context(season, formation_id))
        return render(request, 'suivi/student_list.html', context)

    students = Member.objects.order_by('last_name', 'first_name') if show_all else _students(formation_id)
    students = students.prefetch_related(Prefetch(
        'enrollments', queryset=Enrollment.objects.select_related('formation').filter(status=Enrollment.Status.ACTIVE),
        to_attr='active_enrollments',
    ))
    season_filter = Q(attendances__session__season=season) if season else Q()
    students = students.annotate(
        present_count=Count('attendances', filter=season_filter & Q(attendances__status=Attendance.Status.PRESENT), distinct=True),
        attendance_count=Count('attendances', filter=season_filter, distinct=True),
        acquired_count=Count('member_skills', filter=Q(member_skills__status=MemberSkill.SkillStatus.ACQUIRED), distinct=True),
    )
    rows = []
    for m in students:
        rate = round(100 * m.present_count / m.attendance_count) if m.attendance_count else None
        rows.append({'member': m, 'rate': rate})
    context['rows'] = rows
    return render(request, 'suivi/student_list.html', context)


@club_staff_required
def student_detail(request, pk):
    member = get_object_or_404(Member.objects.select_related('user'), pk=pk)
    comment_form = CommentForm(member=member, initial={'date': timezone.localdate()})
    open_form = None

    if request.method == 'POST':
        action = request.POST.get('_action')

        if action == 'add_comment':
            comment_form = CommentForm(request.POST, member=member)
            if comment_form.is_valid():
                comment_form.save(author=request.user)
                messages.success(request, "Commentaire ajouté.")
                return redirect(reverse('suivi-student-detail', args=[pk]) + '#commentaires')
            open_form = 'comment'

        elif action == 'enroll':
            formation = get_object_or_404(Formation, pk=request.POST.get('formation_id'))
            Enrollment.objects.get_or_create(member=member, formation=formation)
            return redirect(reverse('suivi-student-detail', args=[pk]) + '#infos')

    season = _current_season()
    sheet = _tracking_sheet(member, season)
    return render(request, 'suivi/student_detail.html', {
        'member': member,
        'enrollments': member.enrollments.select_related('formation__cursus'),
        'enrollable_formations': Formation.objects.active()
                                 .exclude(enrollments__member=member).order_by('name'),
        **sheet,
        'last_present': next((a.session.date for a in sheet['attendances'] if a.status == Attendance.Status.PRESENT), None),
        'comments': member.comments.select_related('session', 'skill', 'author'),
        'comment_form': comment_form,
        'open_form': open_form,
        'invite_url': invite_url_for(request, member.user) if member.user_id and not member.user.is_active else None,
        'can_reset_password': member.user_id is not None and can_reset_password(request.user, member.user),
        'season': season,
        'active_tab': 'eleves',
    })


# ---------------------------------------------------------------------------
# Espace élève
# ---------------------------------------------------------------------------

@login_required
def my_tracking(request):
    """Fiche de suivi de l'élève connecté (fiche rattachée à son compte)."""
    members = Member.objects.filter(user=request.user)
    season = _current_season()
    sheets = []
    for member in members:
        sheets.append({
            'member': member,
            **_tracking_sheet(member, season, for_student=True),
            # Les notes équipe ne sont jamais transmises à l'élève.
            'comments': member.comments.visible_to_student().select_related('session', 'skill', 'author'),
        })
    return render(request, 'suivi/my_tracking.html', {
        'sheets': sheets,
        'season': season,
    })


# ---------------------------------------------------------------------------
# Commentaires
# ---------------------------------------------------------------------------

@club_staff_required
def comment_action(request, pk):
    """Modification du texte, suppression, ou bascule visible par l'élève ↔ note équipe d'un commentaire
    (tout encadrant). Retour vers `next`."""
    comment = get_object_or_404(Comment, pk=pk)
    next_url = request.GET.get('next', '')
    if not url_has_allowed_host_and_scheme(next_url, {request.get_host()}, request.is_secure()):
        next_url = reverse('suivi-student-detail', args=[comment.member_id]) + '#commentaires'
    if request.method == 'POST':
        # Boutons éventuellement placés dans un autre formulaire : nom distinct de `_action`.
        action = request.POST.get('comment_action')
        if action == 'edit':
            content = request.POST.get(f'comment_{comment.pk}_content', '').strip()
            if content:
                comment.content = content
                comment.save(update_fields=['content'])
            else:
                messages.error(request, "Le commentaire est vide : utilisez ✕ pour le supprimer.")
        elif action == 'delete':
            comment.delete()
        elif action == 'toggle':
            comment.staff_only = not comment.staff_only
            comment.save(update_fields=['staff_only'])
    return redirect(next_url)
