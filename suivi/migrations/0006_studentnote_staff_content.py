from django.db import migrations, models


def move_staff_notes(apps, schema_editor):
    """Une note « équipe encadrante uniquement » devient une note équipe."""
    StudentNote = apps.get_model('suivi', 'StudentNote')
    for note in StudentNote.objects.filter(visibility='staff'):
        note.staff_content, note.content = note.content, ''
        note.save(update_fields=['content', 'staff_content'])


class Migration(migrations.Migration):

    dependencies = [
        ('suivi', '0005_staff_comment'),
    ]

    operations = [
        migrations.AddField(
            model_name='studentnote',
            name='staff_content',
            field=models.TextField(blank=True, help_text="Réservée à l'équipe encadrante : jamais affichée à l'élève.", verbose_name='Note équipe'),
        ),
        migrations.AlterField(
            model_name='studentnote',
            name='content',
            field=models.TextField(blank=True, help_text="Visible par l'élève dans « Mon suivi ».", verbose_name='Note'),
        ),
        migrations.RunPython(move_staff_notes, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='studentnote',
            name='visibility',
        ),
    ]
