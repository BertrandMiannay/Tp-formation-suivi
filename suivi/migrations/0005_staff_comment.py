from django.db import migrations, models


def move_private_comments(apps, schema_editor):
    """Un commentaire marqué privé devient la note équipe."""
    for model_name in ('Attendance', 'WorkedSkill'):
        Model = apps.get_model('suivi', model_name)
        for obj in Model.objects.filter(comment_private=True).exclude(comment=''):
            obj.staff_comment, obj.comment = obj.comment, ''
            obj.save(update_fields=['comment', 'staff_comment'])


class Migration(migrations.Migration):

    dependencies = [
        ('suivi', '0004_comment_private'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendance',
            name='staff_comment',
            field=models.CharField(blank=True, help_text="Réservée à l'équipe encadrante : jamais affichée à l'élève.", max_length=255, verbose_name='Note équipe'),
        ),
        migrations.AddField(
            model_name='workedskill',
            name='staff_comment',
            field=models.CharField(blank=True, help_text="Réservée à l'équipe encadrante : jamais affichée à l'élève.", max_length=255, verbose_name='Note équipe'),
        ),
        migrations.RunPython(move_private_comments, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='attendance',
            name='comment_private',
        ),
        migrations.RemoveField(
            model_name='workedskill',
            name='comment_private',
        ),
    ]
