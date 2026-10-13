import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copy_comments(apps, schema_editor):
    """Reprend dans `Comment` les commentaires des présences, compétences travaillées, notes et
    évaluations : chaque partie (visible / note équipe) devient un commentaire distinct."""
    Comment = apps.get_model('suivi', 'Comment')
    Attendance = apps.get_model('suivi', 'Attendance')
    WorkedSkill = apps.get_model('suivi', 'WorkedSkill')
    StudentNote = apps.get_model('suivi', 'StudentNote')
    SkillEvaluation = apps.get_model('formation', 'SkillEvaluation')
    seen = set()

    def add(member_id, session_id, skill_id, date, author_id, text, staff_only):
        text = (text or '').strip()
        key = (member_id, session_id, skill_id, text, staff_only)
        if not text or key in seen:
            return None
        seen.add(key)
        return Comment.objects.create(
            member_id=member_id, session_id=session_id, skill_id=skill_id, date=date,
            author_id=author_id, content=text, staff_only=staff_only,
        )

    for a in Attendance.objects.select_related('session').order_by('pk'):
        for text, staff_only in ((a.comment, False), (a.staff_comment, True)):
            add(a.member_id, a.session_id, None, a.session.date, None, text, staff_only)

    for ws in WorkedSkill.objects.select_related('session').order_by('pk'):
        for text, staff_only in ((ws.comment, False), (ws.staff_comment, True)):
            add(ws.member_id, ws.session_id, ws.skill_id, ws.session.date, ws.author_id, text, staff_only)

    for note in StudentNote.objects.order_by('pk'):
        for text, staff_only in ((note.content, False), (note.staff_content, True)):
            comment = add(note.member_id, note.session_id, None, note.date, note.author_id, text, staff_only)
            if comment:
                Comment.objects.filter(pk=comment.pk).update(created_at=note.created_at)

    # Évaluations : celles saisies en séance recopiaient le commentaire de la compétence travaillée
    # (ou « Séance du jj/mm/aaaa » à défaut) ; on les rattache à la séance et on écarte les doublons.
    sessions = {}
    for ws in WorkedSkill.objects.select_related('session'):
        sessions.setdefault((ws.member_id, ws.skill_id, ws.session.date), ws.session_id)
    for ev in SkillEvaluation.objects.order_by('pk'):
        session_id = sessions.get((ev.member_id, ev.skill_id, ev.date))
        comment = ev.comment
        if comment == f"Séance du {ev.date:%d/%m/%Y}":
            comment = ''
        for text, staff_only in ((comment, False), (ev.staff_comment, True)):
            add(ev.member_id, session_id, ev.skill_id, ev.date, ev.author_id, text, staff_only)


class Migration(migrations.Migration):

    dependencies = [
        ('formation', '0003_staff_comment'),
        ('suivi', '0007_remove_excused_status'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Comment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('content', models.TextField(verbose_name='Commentaire')),
                ('staff_only', models.BooleanField(default=False, help_text="Réservée à l'équipe encadrante : jamais affichée à l'élève.", verbose_name='Note équipe')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Auteur')),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comments', to='formation.member', verbose_name='Élève')),
                ('session', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='comments', to='suivi.trainingsession', verbose_name='Séance')),
                ('skill', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='comments', to='formation.skill', verbose_name='Compétence')),
            ],
            options={
                'verbose_name': 'Commentaire',
                'verbose_name_plural': 'Commentaires',
                'ordering': ['-date', '-pk'],
            },
        ),
        migrations.RunPython(copy_comments, migrations.RunPython.noop),
    ]
