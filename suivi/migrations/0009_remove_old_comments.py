from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('suivi', '0008_comment'),
    ]

    operations = [
        migrations.RemoveField(model_name='attendance', name='comment'),
        migrations.RemoveField(model_name='attendance', name='staff_comment'),
        migrations.RemoveField(model_name='workedskill', name='comment'),
        migrations.RemoveField(model_name='workedskill', name='staff_comment'),
        migrations.DeleteModel(name='StudentNote'),
    ]
