import io
import json
import logging
from datetime import date
from urllib.parse import quote
from xml.sax.saxutils import escape

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.text import slugify

from formation.forms import FormationForm, QuickStudentForm, StudentForm, StudentImportForm, attachable_accounts
from formation.models import (
    Season, Cursus, CursusCategory, Skill, Member, MemberSkill, SkillEvaluation, Formation, Enrollment,
)
from suivi.forms import add_comments
from suivi.models import Comment, TrainingSession
from suivi.views import attendance_matrix
from userManagement.views import (
    admin_required, can_manage_account, can_view_invitation, club_staff_required, create_invited_user,
    renew_invitation,
)
from userManagement.models import Role

logger = logging.getLogger(__name__)


def _parse_iso_date(value):
    """Date AAAA-MM-JJ saisie dans un formulaire de cursus, ou None si le format est invalide."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Élèves
# ---------------------------------------------------------------------------

def attach_account(member, email):
    """Rattache un compte à l'élève : compte existant sans fiche (ex. encadrant qui suit une formation)
    ou nouveau compte inactif avec lien d'invitation."""
    user = attachable_accounts().filter(email__iexact=email).first()
    if user is None:
        user = create_invited_user(email, group_name=Role.STUDENT)
    member.user = user
    member.save(update_fields=['user'])
    return user


def deletes_student_account(actor, member):
    """Supprimer la fiche supprime aussi le compte rattaché s'il s'agit d'un compte élève ; un compte
    encadrant / administrateur (qui suit une formation) est conservé."""
    user = member.user if member.user_id else None
    return user is not None and user.role == Role.STUDENT and can_manage_account(actor, user)


@club_staff_required
def student_create(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            formation = form.cleaned_data['formation']
            account = form.cleaned_data['account']
            with transaction.atomic():
                member = form.save()
                if account:
                    member.user = user = account
                    member.save(update_fields=['user'])
                else:
                    user = attach_account(member, email) if email else None
                if formation:
                    Enrollment.objects.create(member=member, formation=formation)
            logger.info("STUDENT_CREATE pk=%s user=%s by=%s", member.pk, user.pk if user else None, request.user.username)
            messages.success(request, f"Élève {member} créé." + (
                " Transmettez-lui le lien d'invitation pour qu'il choisisse son mot de passe."
                if user and not user.is_active else ""
            ))
            return redirect('suivi-student-detail', pk=member.pk)
    else:
        form = StudentForm(initial={'formation': request.GET.get('formation'), 'account': request.GET.get('user')})
    return render(request, 'formation/student_form.html', {'form': form, 'member': None})


@club_staff_required
def student_edit(request, pk):
    member = get_object_or_404(Member, pk=pk)
    if request.method == 'POST':
        if request.POST.get('_action') == 'renew_invite':
            if member.user_id and can_view_invitation(request.user, member.user):
                renew_invitation(member.user)
                messages.success(request, "Nouveau lien d'invitation généré (valable 7 jours).")
            return redirect(reverse('suivi-student-detail', args=[pk]) + '#infos')
        form = StudentForm(request.POST, instance=member)
        if form.is_valid():
            email = form.cleaned_data['email']
            with transaction.atomic():
                form.save()
                if member.user_id is None:
                    if email:
                        attach_account(member, email)
                elif form.manages_account_email and member.user.email != email:
                    member.user.email = email
                    member.user.save(update_fields=['email'])
            logger.info("STUDENT_EDIT pk=%s by=%s", member.pk, request.user.username)
            messages.success(request, "Fiche élève mise à jour.")
            return redirect(reverse('suivi-student-detail', args=[pk]) + '#infos')
    else:
        form = StudentForm(instance=member)
    return render(request, 'formation/student_form.html', {
        'form': form, 'member': member, 'delete_account': deletes_student_account(request.user, member),
    })


@club_staff_required
def student_import(request):
    """Création de plusieurs élèves d'un coup (nom, prénom, email facultatif), avec inscription facultative."""
    form = StudentImportForm(request.POST or None, initial={'formation': request.GET.get('formation')})
    if request.method == 'POST' and form.is_valid():
        formation = form.cleaned_data['formation']
        invited = 0
        with transaction.atomic():
            members = []
            for row in form.cleaned_data['lines']:
                member = Member.objects.create(first_name=row['first_name'], last_name=row['last_name'])
                if row['email'] and not attach_account(member, row['email']).is_active:
                    invited += 1
                if formation:
                    Enrollment.objects.create(member=member, formation=formation)
                members.append(member)
        logger.info("STUDENT_IMPORT count=%s formation=%s by=%s",
                    len(members), formation.pk if formation else None, request.user.username)
        messages.success(request, f"{len(members)} élève(s) importé(s)" + (
            f", inscrit(s) à « {formation} »." if formation else "."
        ) + (
            f" {invited} compte(s) élève créé(s) : les liens d'invitation sont sur leurs fiches."
            if invited else ""
        ))
        if formation:
            return redirect(reverse('formation-detail', args=[formation.pk]) + '#eleves')
        return redirect(reverse('suivi-students') + '?formation=all')
    return render(request, 'formation/student_import.html', {'form': form, 'active_tab': 'eleves'})


@club_staff_required
def student_delete(request, pk):
    """Supprime la fiche et tout son suivi (inscriptions, présences, compétences, notes)."""
    member = get_object_or_404(Member.objects.select_related('user'), pk=pk)
    if request.method != 'POST':
        return redirect('eleve-edit', pk=pk)
    user = member.user
    delete_account = deletes_student_account(request.user, member)
    with transaction.atomic():
        logger.info("STUDENT_DELETE pk=%s name=%s user=%s account_deleted=%s by=%s",
                    member.pk, member, user.pk if user else None, delete_account, request.user.username)
        member.delete()
        if delete_account:
            user.delete()
    messages.success(request, f"Fiche de {member} supprimée.")
    return redirect('suivi-students')


@club_staff_required
def evaluation(request, pk):
    member = get_object_or_404(Member, pk=pk)
    formations_qs = Cursus.objects.filter(pk__in=member.cursus_ids()).prefetch_related('categories__skills').order_by('name')
    skill_ids = [s.pk for f in formations_qs for c in f.categories.all() for s in c.skills.all()]
    member_skills_map = {
        ms.skill_id: ms.status
        for ms in MemberSkill.objects.filter(member=member, skill_id__in=skill_ids)
    }
    # Historique par compétence : évaluations et commentaires (avec ou sans séance), plus récents d'abord.
    evaluations_map = {}
    for ev in SkillEvaluation.objects.filter(member=member, skill_id__in=skill_ids).select_related('author'):
        evaluations_map.setdefault(ev.skill_id, []).append({
            'kind': 'evaluation',
            'pk': ev.pk,
            'author': (ev.author.get_full_name() or ev.author.username) if ev.author else '',
            'date': ev.date,
            'status': ev.status,
            'status_display': ev.get_status_display(),
        })
    for c in Comment.objects.filter(member=member, skill_id__in=skill_ids).select_related('session', 'author'):
        evaluations_map.setdefault(c.skill_id, []).append({'kind': 'comment', 'pk': c.pk, 'date': c.date, 'comment': c})
    for history in evaluations_map.values():
        history.sort(key=lambda e: (e['date'], e['kind'] == 'comment', e['pk']), reverse=True)
    formations = []
    for cursus in formations_qs:
        categories = []
        for category in cursus.categories.all():
            skills = [
                {
                    'pk': s.pk,
                    'name': s.name,
                    'status': member_skills_map.get(s.pk, MemberSkill.SkillStatus.NOT_ACQUIRED),
                    'evaluations': evaluations_map.get(s.pk, []),
                }
                for s in category.skills.all()
            ]
            categories.append({'name': category.name, 'skills': skills})
        formations.append({'pk': cursus.pk, 'name': cursus.name, 'categories': categories})
    return render(request, 'formation/evaluation.html', {
        'member': member,
        'formations': formations,
        'status_choices': MemberSkill.SkillStatus.choices,
        'active_tab': 'eleves',
    })


# ---------------------------------------------------------------------------
# Formations et inscriptions
# ---------------------------------------------------------------------------

@club_staff_required
def formation_list(request):
    formations = Formation.objects.select_related('cursus').prefetch_related('managers').annotate(
        student_count=Count('enrollments', filter=Q(enrollments__status=Enrollment.Status.ACTIVE)),
    )
    return render(request, 'formation/formation_list.html', {
        'active_formations': [f for f in formations if f.status == Formation.Status.ACTIVE],
        'closed_formations': [f for f in formations if f.status == Formation.Status.CLOSED],
        'active_tab': 'formations',
    })


@admin_required
def formation_create(request):
    form = FormationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        formation = form.save()
        logger.info("FORMATION_CREATE pk=%s name=%s by=%s", formation.pk, formation.name, request.user.username)
        messages.success(request, f"Formation « {formation} » créée.")
        return redirect('formation-detail', pk=formation.pk)
    return render(request, 'formation/formation_form.html', {'form': form, 'active_tab': 'formations'})


@club_staff_required
def formation_detail(request, pk):
    formation = get_object_or_404(Formation.objects.select_related('cursus').prefetch_related('managers'), pk=pk)
    edit_form = FormationForm(instance=formation) if request.user.is_administrator else None
    quick_form = QuickStudentForm()
    anchor = reverse('formation-detail', args=[pk]) + '#eleves'

    if request.method == 'POST':
        action = request.POST.get('_action')

        if action == 'enroll':
            member = get_object_or_404(Member, pk=request.POST.get('member_id'))
            _, created = Enrollment.objects.get_or_create(member=member, formation=formation)
            if created:
                messages.success(request, f"{member} inscrit à la formation.")
            return redirect(anchor)

        elif action == 'create_student':
            quick_form = QuickStudentForm(request.POST)
            if quick_form.is_valid():
                member = quick_form.save(formation=formation)
                logger.info("STUDENT_CREATE pk=%s formation=%s by=%s", member.pk, formation.pk, request.user.username)
                messages.success(request, f"Élève {member} créé et inscrit.")
                return redirect(anchor)

        elif action == 'set_status':
            enrollment = get_object_or_404(Enrollment, pk=request.POST.get('enrollment_pk'), formation=formation)
            status = request.POST.get('status')
            if status in Enrollment.Status.values:
                enrollment.status = status
                enrollment.save(update_fields=['status'])
            return redirect(anchor)

        elif action == 'unenroll':
            Enrollment.objects.filter(pk=request.POST.get('enrollment_pk'), formation=formation).delete()
            return redirect(anchor)

        elif action == 'edit' and request.user.is_administrator:
            edit_form = FormationForm(request.POST, instance=formation)
            if edit_form.is_valid():
                edit_form.save()
                messages.success(request, "Formation mise à jour.")
                return redirect('formation-detail', pk=pk)

        elif action == 'toggle_status' and request.user.is_administrator:
            formation.status = (
                Formation.Status.CLOSED if formation.status == Formation.Status.ACTIVE else Formation.Status.ACTIVE
            )
            formation.save(update_fields=['status'])
            logger.info("FORMATION_STATUS pk=%s status=%s by=%s", formation.pk, formation.status, request.user.username)
            return redirect('formation-detail', pk=pk)

    enrollments = formation.enrollments.select_related('member__user').order_by('member__last_name', 'member__first_name')
    skill_total = Skill.objects.filter(category__cursus=formation.cursus_id).count()
    acquired = {
        row['member_id']: row['n']
        for row in MemberSkill.objects.filter(
            member__in=[e.member_id for e in enrollments], skill__category__cursus=formation.cursus_id,
            status=MemberSkill.SkillStatus.ACQUIRED,
        ).values('member_id').annotate(n=Count('pk'))
    }
    rows = [{
        'enrollment': e,
        'acquired': acquired.get(e.member_id, 0),
        'pct': round(100 * acquired.get(e.member_id, 0) / skill_total) if skill_total else 0,
    } for e in enrollments]
    addable_members = Member.objects.exclude(enrollments__formation=formation).order_by('last_name', 'first_name')
    sessions = list(formation.training_sessions.order_by('date', 'pk'))
    return render(request, 'formation/formation_detail.html', {
        'formation': formation,
        'rows': rows,
        'skill_total': skill_total,
        'status_choices': Enrollment.Status.choices,
        'addable_members': addable_members,
        'quick_form': quick_form,
        'edit_form': edit_form,
        'sessions': sessions,
        'attendance_rows': attendance_matrix(sessions, [e.member for e in enrollments]),
        'active_tab': 'formations',
    })


# ---------------------------------------------------------------------------
# Saisons et cursus (administration)
# ---------------------------------------------------------------------------

@admin_required
def season_gestion(request):
    form_data = {}
    if request.method == 'POST':
        label = request.POST.get('label', '').strip()
        if label:
            Season.objects.create(label=label)
            return redirect('saison-gestion')
        form_data = {'label': label}
    seasons = Season.objects.all().order_by('-current', 'label')
    return render(request, 'formation/season_gestion.html', {
        'seasons': seasons,
        'form_data': form_data,
        'active_tab': 'gestion',
    })


@admin_required
def set_current_season(request, pk):
    if request.method == 'POST':
        season = get_object_or_404(Season, pk=pk)
        with transaction.atomic():
            Season.objects.update(current=False)
            Season.objects.filter(pk=season.pk).update(current=True)
            # Séances créées sans saison en cours : rattachées à la saison activée,
            # sinon elles disparaîtraient de la liste filtrée sur la saison en cours.
            attached = TrainingSession.objects.filter(season__isnull=True).update(season=season)
        if attached:
            logger.info("SEASON_ATTACH_SESSIONS season=%s count=%s by=%s", season.pk, attached, request.user.username)
            messages.info(request, f"{attached} séance(s) sans saison rattachée(s) à {season}.")
    return redirect('saison-gestion')


@admin_required
def delete_season(request, pk):
    if request.method == 'POST':
        season = Season.objects.filter(pk=pk).first()
        if season:
            logger.info("SEASON_DELETE pk=%s label=%s by=%s", pk, season.label, request.user.username)
            season.delete()
    return redirect('saison-gestion')


@admin_required
def cursus_list(request):
    cursus_list = Cursus.objects.annotate(
        category_count=Count('categories'),
    ).order_by('status', '-date')
    in_use = Cursus.in_use_ids()
    for cursus in cursus_list:
        cursus.deletable = cursus.pk not in in_use
    return render(request, 'formation/cursus_list.html', {
        'cursus_list': cursus_list,
        'active_tab': 'cursus',
    })


@admin_required
def cursus_create(request):
    error = None
    form_data = {}
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        date_str = request.POST.get('date', '').strip()
        form_data = {'name': name, 'date': date_str}
        if not name:
            error = "Le nom du cursus est obligatoire."
        elif not date_str:
            error = "La date de version est obligatoire."
        elif (parsed_date := _parse_iso_date(date_str)) is None:
            error = "Format de date invalide (attendu : AAAA-MM-JJ)."
        else:
            cursus = Cursus.objects.create(name=name, date=parsed_date)
            logger.info("CURSUS_CREATE pk=%s name=%s by=%s", cursus.pk, cursus.name, request.user.username)
            messages.success(request, f"Cursus « {cursus.name} » créé.")
            return redirect('saison-cursus-detail', pk=cursus.pk)
    return render(request, 'formation/cursus_create.html', {
        'error': error,
        'form_data': form_data,
        'active_tab': 'cursus',
    })


@admin_required
def cursus_detail(request, pk):
    cursus = get_object_or_404(Cursus, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('_action')

        if action == 'edit_cursus':
            name = request.POST.get('name', '').strip()
            date_str = request.POST.get('date', '').strip()
            if name and date_str:
                parsed_date = _parse_iso_date(date_str)
                if parsed_date is None:
                    messages.error(request, "Format de date invalide.")
                else:
                    cursus.name, cursus.date = name, parsed_date
                    cursus.save(update_fields=['name', 'date'])
                    messages.success(request, "Cursus mis à jour.")
            return redirect('saison-cursus-detail', pk=pk)

        elif action == 'add_category':
            name = request.POST.get('category_name', '').strip()
            if name:
                max_order = cursus.categories.aggregate(m=Max('order'))['m'] or 0
                CursusCategory.objects.create(cursus=cursus, name=name, order=max_order + 1)
            return redirect('saison-cursus-detail', pk=pk)

        elif action == 'delete_category':
            cat_pk = request.POST.get('category_pk')
            CursusCategory.objects.filter(pk=cat_pk, cursus=cursus).delete()
            return redirect('saison-cursus-detail', pk=pk)

        elif action == 'reorder_categories':
            order_list = request.POST.getlist('category_order')
            with transaction.atomic():
                for i, cat_pk in enumerate(order_list, start=1):
                    CursusCategory.objects.filter(pk=cat_pk, cursus=cursus).update(order=i)
            return redirect('saison-cursus-detail', pk=pk)

        elif action == 'add_skill':
            cat_pk = request.POST.get('category_pk')
            name = request.POST.get('skill_name', '').strip()
            if name and cat_pk:
                category = get_object_or_404(CursusCategory, pk=cat_pk, cursus=cursus)
                max_order = category.skills.aggregate(m=Max('order'))['m'] or 0
                Skill.objects.create(category=category, name=name, order=max_order + 1)
            return redirect('saison-cursus-detail', pk=pk)

        elif action == 'delete_skill':
            skill_pk = request.POST.get('skill_pk')
            Skill.objects.filter(pk=skill_pk, category__cursus=cursus).delete()
            return redirect('saison-cursus-detail', pk=pk)

        elif action == 'reorder_skills':
            cat_pk = request.POST.get('category_pk')
            order_list = request.POST.getlist('skill_order')
            with transaction.atomic():
                for i, skill_pk in enumerate(order_list, start=1):
                    Skill.objects.filter(pk=skill_pk, category_id=cat_pk).update(order=i)
            return redirect('saison-cursus-detail', pk=pk)

    categories = cursus.categories.prefetch_related('skills').all()
    return render(request, 'formation/cursus_detail.html', {
        'cursus': cursus,
        'categories': categories,
        'cursus_json': _cursus_json(cursus, categories),
        'active_tab': 'cursus',
    })


def _cursus_json(cursus, categories=None):
    """Cursus au format JSON d'import (`cursus_import_json`) : nom, date, catégories et compétences dans l'ordre."""
    if categories is None:
        categories = cursus.categories.prefetch_related('skills')
    return json.dumps({
        'name': cursus.name,
        'date': cursus.date.isoformat(),
        'categories': [
            {'name': cat.name, 'skills': [{'name': skill.name} for skill in cat.skills.all()]}
            for cat in categories
        ],
    }, indent=2, ensure_ascii=False)


@admin_required
def cursus_export_json(request, pk):
    """Téléchargement du cursus en fichier .json, réimportable tel quel."""
    cursus = get_object_or_404(Cursus, pk=pk)
    filename = f"cursus-{slugify(cursus.name) or cursus.pk}-{cursus.date.isoformat()}.json"
    response = HttpResponse(_cursus_json(cursus), content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@admin_required
def cursus_archive(request, pk):
    if request.method == 'POST':
        cursus = get_object_or_404(Cursus, pk=pk)
        if cursus.status == Cursus.Status.ACTIVE:
            cursus.status = Cursus.Status.ARCHIVED
            action_label = "archivé"
        else:
            cursus.status = Cursus.Status.ACTIVE
            action_label = "réactivé"
        cursus.save(update_fields=['status'])
        logger.info("CURSUS_STATUS pk=%s status=%s by=%s", cursus.pk, cursus.status, request.user.username)
        messages.success(request, f"Cursus « {cursus.name} » {action_label}.")
    return redirect('saison-cursus')


@admin_required
def cursus_delete(request, pk):
    """Suppression définitive d'un cursus (catégories, compétences et formations sans inscrit),
    refusée dès qu'un élève y est inscrit ou y a un suivi."""
    if request.method == 'POST':
        cursus = get_object_or_404(Cursus, pk=pk)
        if not cursus.is_deletable():
            messages.error(request, f"Le cursus « {cursus.name} » ne peut pas être supprimé : des élèves y sont inscrits "
                                    "ou y ont déjà un suivi. Archivez-le plutôt.")
        else:
            with transaction.atomic():
                cursus.formations.all().delete()
                cursus.delete()
            logger.info("CURSUS_DELETE pk=%s name=%s by=%s", pk, cursus.name, request.user.username)
            messages.success(request, f"Cursus « {cursus.name} » supprimé.")
    return redirect('saison-cursus')


@admin_required
def cursus_import_json(request):
    error = None
    json_text = ''
    if request.method == 'POST':
        json_text = request.POST.get('json_data', '').strip()
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            error = f"JSON invalide : {e}"
        else:
            if not isinstance(data, dict):
                data = {}
            name = str(data.get('name', '')).strip()
            date_str = str(data.get('date', '')).strip()
            categories_raw = data.get('categories', [])
            if not name:
                error = "Le champ « name » est obligatoire."
            elif not date_str:
                error = "Le champ « date » est obligatoire (format AAAA-MM-JJ)."
            elif not isinstance(categories_raw, list):
                error = "Le champ « categories » doit être une liste."
            elif (parsed_date := _parse_iso_date(date_str)) is None:
                error = "Format de date invalide (attendu : AAAA-MM-JJ)."
            else:
                with transaction.atomic():
                    cursus = Cursus.objects.create(name=name, date=parsed_date)
                    for cat_order, cat_data in enumerate(categories_raw, start=1):
                        cat_name = str(cat_data.get('name', '')).strip() if isinstance(cat_data, dict) else ''
                        if not cat_name:
                            continue
                        category = CursusCategory.objects.create(
                            cursus=cursus, name=cat_name, order=cat_order
                        )
                        skills_raw = cat_data.get('skills', [])
                        for skill_order, skill_data in enumerate(skills_raw if isinstance(skills_raw, list) else [], start=1):
                            skill_name = str(skill_data.get('name', '')).strip() if isinstance(skill_data, dict) else ''
                            if skill_name:
                                Skill.objects.create(
                                    category=category, name=skill_name, order=skill_order
                                )
                logger.info("CURSUS_IMPORT pk=%s name=%s by=%s", cursus.pk, cursus.name, request.user.username)
                messages.success(request, f"Cursus « {cursus.name} » importé avec succès.")
                return redirect('saison-cursus-detail', pk=cursus.pk)
    return render(request, 'formation/formation_import.html', {
        'error': error,
        'json_text': json_text,
        'active_tab': 'importer',
    })


@club_staff_required
def evaluation_save(request, pk, cursus_pk):
    if request.method != 'POST':
        return redirect('eleve-evaluation', pk=pk)
    member = get_object_or_404(Member, pk=pk)
    cursus = get_object_or_404(Cursus, pk=cursus_pk)
    valid_statuses = set(dict(MemberSkill.SkillStatus.choices))
    skills = Skill.objects.filter(category__cursus=cursus)
    today = timezone.localdate()
    current = {
        ms.skill_id: ms.status
        for ms in MemberSkill.objects.filter(member=member, skill__in=skills)
    }
    for skill in skills:
        status = request.POST.get(f'skill_{skill.pk}_status', MemberSkill.SkillStatus.NOT_ACQUIRED)
        if status not in valid_statuses:
            status = MemberSkill.SkillStatus.NOT_ACQUIRED
        MemberSkill.objects.update_or_create(
            member=member, skill=skill,
            defaults={'status': status},
        )
        if status != current.get(skill.pk, MemberSkill.SkillStatus.NOT_ACQUIRED):
            SkillEvaluation.objects.create(
                member=member, skill=skill, date=today, status=status, author=request.user,
            )
        add_comments(
            member=member, skill=skill, date=today, author=request.user,
            content=request.POST.get(f'skill_{skill.pk}_comment', ''),
            staff_content=request.POST.get(f'skill_{skill.pk}_staff_comment', ''),
        )
    return redirect('eleve-evaluation', pk=pk)


def _pdf_response(buf, raw_name):
    safe_ascii = raw_name.replace('"', '').replace('\n', '').replace('\r', '')
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = (
        f"attachment; filename=\"{safe_ascii}\"; filename*=UTF-8''{quote(raw_name)}"
    )
    return response


def _build_evaluation_pdf(cursus, member=None, subtitle=None):
    """Fiche d'évaluation PDF d'un cursus. Avec `member` : statut et commentaires de l'élève ;
    sans : modèle vierge à remplir à la main (cases à cocher par statut, commentaires vides)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    categories = cursus.categories.prefetch_related('skills')
    member_skills = {}
    comments_by_skill = {}
    if member is not None:
        member_skills = {
            ms.skill_id: ms
            for ms in MemberSkill.objects.filter(member=member, skill__category__cursus=cursus)
        }
        # Document remis à l'élève : les notes équipe n'y figurent pas.
        for c in (
            Comment.objects.visible_to_student().filter(member=member, skill__category__cursus=cursus)
            .select_related('author')
        ):
            comments_by_skill.setdefault(c.skill_id, []).append(c)

    styles = getSampleStyleSheet()
    small = ParagraphStyle('small', parent=styles['Normal'], fontSize=8, leading=10)
    small_grey = ParagraphStyle('small_grey', parent=small, textColor=colors.HexColor('#6b7280'))
    bold_cat = ParagraphStyle('bold_cat', parent=styles['Normal'], fontSize=9, leading=11, fontName='Helvetica-Bold')
    header_style = ParagraphStyle('header', parent=styles['Normal'], fontSize=8, leading=10, fontName='Helvetica-Bold',
                                  textColor=colors.white)
    header_center = ParagraphStyle('header_center', parent=header_style, alignment=1)

    if member is not None:
        col_widths = [8 * cm, 3 * cm, 7.5 * cm]
        header = [
            Paragraph('Compétence', header_style),
            Paragraph('Statut', header_style),
            Paragraph('Commentaires', header_style),
        ]
    else:
        # Une colonne à cocher par statut.
        col_widths = [7 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm, 6.1 * cm]
        header = [
            Paragraph('Compétence', header_style),
            *(Paragraph(label, header_center) for label in ('Non acquis', 'En cours', 'Acquis')),
            Paragraph('Commentaires', header_style),
        ]
    n_cols = len(col_widths)
    table_data = [header]

    row_styles = []
    current_row = 1

    for category in categories:
        table_data.append([Paragraph(escape(category.name), bold_cat)] + [''] * (n_cols - 1))
        row_styles.append(('BACKGROUND', (0, current_row), (-1, current_row), colors.HexColor('#f3f4f6')))
        row_styles.append(('SPAN', (0, current_row), (-1, current_row)))
        current_row += 1

        for skill in category.skills.all():
            if member is None:
                table_data.append([Paragraph(escape(skill.name), small)] + [''] * (n_cols - 1))
                # Hauteur suffisante pour écrire à la main.
                row_styles.append(('BOTTOMPADDING', (0, current_row), (-1, current_row), 14))
                current_row += 1
                continue
            ms = member_skills.get(skill.pk)
            status_label = (ms.get_status_display() if ms
                            else MemberSkill.SkillStatus.NOT_ACQUIRED.label)
            comment_lines = []
            for c in comments_by_skill.get(skill.pk, []):
                date_str = date_format(c.date, 'd/m/Y')
                if c.author:
                    date_str += f" · {escape(c.author.get_full_name() or c.author.username)}"
                comment_lines.append(f"<font color='#9ca3af'>{date_str}</font> {escape(c.content)}")
            comment_para = Paragraph('<br/>'.join(comment_lines), small_grey) if comment_lines else ''

            table_data.append([
                Paragraph(escape(skill.name), small),
                Paragraph(status_label, small),
                comment_para,
            ])
            current_row += 1

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, 0),  colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR',    (0, 0), (-1, 0),  colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
        ('GRID',         (0, 0), (-1, -1), 0.4, colors.HexColor('#e5e7eb')),
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',   (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
        ('LEFTPADDING',  (0, 0), (-1, -1), 6),
        *row_styles,
    ]))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )

    title_style = ParagraphStyle('title', parent=styles['Heading1'], fontSize=14, spaceAfter=12)
    info_style = ParagraphStyle('info', parent=styles['Normal'], fontSize=10, leading=14, spaceAfter=12)

    story = [Paragraph(escape(cursus.name), title_style)]
    if subtitle:
        story.append(Paragraph(escape(subtitle), info_style))
    if member is None:
        story.append(Paragraph(
            'Élève : ' + '_' * 45 + '&nbsp;&nbsp;&nbsp;Date : ' + '_' * 20, info_style,
        ))
    story.append(table)
    doc.build(story)
    buf.seek(0)
    return buf


@club_staff_required
def evaluation_export(request, pk, cursus_pk):
    member = get_object_or_404(Member, pk=pk)
    cursus = get_object_or_404(Cursus, pk=cursus_pk)
    buf = _build_evaluation_pdf(cursus, member=member)
    return _pdf_response(buf, f"evaluation_{member.last_name}_{member.first_name}_{cursus.name}.pdf")


@club_staff_required
def cursus_blank_export(request, pk):
    """Fiche d'évaluation vierge d'un cursus (PDF à imprimer)."""
    cursus = get_object_or_404(Cursus, pk=pk)
    buf = _build_evaluation_pdf(cursus)
    return _pdf_response(buf, f"fiche_vierge_{cursus.name}.pdf")


@club_staff_required
def formation_blank_export(request, pk):
    """Fiche d'évaluation vierge du cursus d'une formation, avec le nom et les dates de la formation."""
    formation = get_object_or_404(Formation.objects.select_related('cursus'), pk=pk)
    subtitle = f"Formation : {formation.name}"
    if formation.start_date:
        subtitle += f" · du {date_format(formation.start_date, 'd/m/Y')}"
    if formation.end_date:
        subtitle += f" au {date_format(formation.end_date, 'd/m/Y')}"
    buf = _build_evaluation_pdf(formation.cursus, subtitle=subtitle)
    return _pdf_response(buf, f"fiche_vierge_{formation.name}.pdf")


@club_staff_required
def evaluation_delete(request, pk, ev_pk):
    if request.method != 'POST':
        return redirect('eleve-evaluation', pk=pk)
    get_object_or_404(SkillEvaluation, pk=ev_pk, member__pk=pk).delete()
    return redirect('eleve-evaluation', pk=pk)
