from django.db import migrations


def attach_orphan_sessions(apps, schema_editor):
    """Rattache à la saison en cours les séances créées alors qu'aucune saison n'était active."""
    Season = apps.get_model('formation', 'Season')
    TrainingSession = apps.get_model('suivi', 'TrainingSession')
    season = Season.objects.filter(current=True).first()
    if season:
        TrainingSession.objects.filter(season__isnull=True).update(season=season)


class Migration(migrations.Migration):

    dependencies = [
        ('formation', '0001_initial'),
        ('suivi', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(attach_orphan_sessions, migrations.RunPython.noop),
    ]
