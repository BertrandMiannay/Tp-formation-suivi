from django.db import migrations


def create_default_club(apps, schema_editor):
    Club = apps.get_model('clubs', 'Club')
    if not Club.objects.exists():
        Club.objects.create(name='Club')


class Migration(migrations.Migration):
    """Club par défaut, auquel les données existantes sont rattachées (formation 0005, suivi 0010)."""

    dependencies = [
        ('clubs', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_default_club, migrations.RunPython.noop),
    ]
