import django.db.models.deletion
from django.db import migrations, models

import clubs.models


MODELS = {'season': 'seasons', 'cursus': 'cursus', 'formation': 'formations', 'member': 'members'}


def attach_to_default_club(apps, schema_editor):
    club = apps.get_model('clubs', 'Club').objects.order_by('pk').first()
    for name in MODELS:
        apps.get_model('formation', name).objects.filter(club__isnull=True).update(club=club)


class Migration(migrations.Migration):
    """Rattache saisons, cursus, formations et élèves à un club (les données existantes au club par défaut)."""

    dependencies = [
        ('clubs', '0002_default_club'),
        ('formation', '0004_remove_skillevaluation_comments'),
    ]

    operations = [
        *[migrations.AddField(
            model_name=name,
            name='club',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name=related_name, to='clubs.club', verbose_name='Club'),
        ) for name, related_name in MODELS.items()],
        migrations.RunPython(attach_to_default_club, migrations.RunPython.noop),
        *[migrations.AlterField(
            model_name=name,
            name='club',
            field=models.ForeignKey(default=clubs.models.get_default_club, on_delete=django.db.models.deletion.CASCADE,
                                    related_name=related_name, to='clubs.club', verbose_name='Club'),
        ) for name, related_name in MODELS.items()],
    ]
