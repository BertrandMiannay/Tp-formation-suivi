from django.db import migrations, models


def keep_one_current_season(apps, schema_editor):
    """Avant la contrainte : si plusieurs saisons sont marquées en cours, seule la dernière créée le reste."""
    Season = apps.get_model('formation', 'Season')
    current = list(Season.objects.filter(current=True).order_by('-pk').values_list('pk', flat=True))
    if len(current) > 1:
        Season.objects.filter(pk__in=current[1:]).update(current=False)


class Migration(migrations.Migration):

    dependencies = [
        ('formation', '0003_staff_comment'),
    ]

    operations = [
        migrations.RunPython(keep_one_current_season, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='season',
            constraint=models.UniqueConstraint(
                condition=models.Q(('current', True)),
                fields=('current',),
                name='single_current_season',
                violation_error_message='Une seule saison peut être en cours.',
            ),
        ),
    ]
