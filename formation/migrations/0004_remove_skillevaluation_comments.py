from django.db import migrations


class Migration(migrations.Migration):
    """Les commentaires des évaluations sont repris dans `suivi.Comment` (suivi 0008)."""

    dependencies = [
        ('formation', '0003_staff_comment'),
        ('suivi', '0008_comment'),
    ]

    operations = [
        migrations.RemoveField(model_name='skillevaluation', name='comment'),
        migrations.RemoveField(model_name='skillevaluation', name='staff_comment'),
    ]
