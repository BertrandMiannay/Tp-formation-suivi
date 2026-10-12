from django.db import migrations, models


def move_private_comments(apps, schema_editor):
    """Un commentaire marqué privé devient la note équipe."""
    SkillEvaluation = apps.get_model('formation', 'SkillEvaluation')
    for ev in SkillEvaluation.objects.filter(comment_private=True).exclude(comment=''):
        ev.staff_comment, ev.comment = ev.comment, ''
        ev.save(update_fields=['comment', 'staff_comment'])


class Migration(migrations.Migration):

    dependencies = [
        ('formation', '0002_skillevaluation_comment_private'),
    ]

    operations = [
        migrations.AddField(
            model_name='skillevaluation',
            name='staff_comment',
            field=models.TextField(blank=True, help_text="Réservée à l'équipe encadrante : jamais affichée à l'élève.", verbose_name='Note équipe'),
        ),
        migrations.RunPython(move_private_comments, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='skillevaluation',
            name='comment_private',
        ),
    ]
