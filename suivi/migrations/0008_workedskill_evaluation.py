import django.db.models.deletion
from django.db import migrations, models


def link_evaluations(apps, schema_editor):
    """Relie chaque compétence évaluée en séance à l'évaluation qu'elle a créée : même élève, même
    compétence, même statut, datée du jour de la séance (la plus récente si plusieurs)."""
    WorkedSkill = apps.get_model('suivi', 'WorkedSkill')
    SkillEvaluation = apps.get_model('formation', 'SkillEvaluation')
    linked = set()
    for ws in WorkedSkill.objects.exclude(status='').select_related('session').order_by('pk'):
        ev = (
            SkillEvaluation.objects
            .filter(member_id=ws.member_id, skill_id=ws.skill_id, date=ws.session.date, status=ws.status)
            .exclude(pk__in=linked).order_by('-pk').first()
        )
        if ev:
            linked.add(ev.pk)
            ws.evaluation_id = ev.pk
            ws.save(update_fields=['evaluation'])


class Migration(migrations.Migration):

    dependencies = [
        ('formation', '0004_single_current_season'),
        ('suivi', '0007_remove_excused_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='workedskill',
            name='evaluation',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='worked_skill',
                to='formation.skillevaluation',
                verbose_name='Évaluation',
            ),
        ),
        migrations.RunPython(link_evaluations, migrations.RunPython.noop),
    ]
