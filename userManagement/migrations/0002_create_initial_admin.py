import os

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations


def create_initial_admin(apps, schema_editor):
    """Crée le premier administrateur à partir de DJANGO_SUPERUSER_USERNAME / _PASSWORD / _EMAIL.

    Sans nom ou mot de passe, ou si le compte existe déjà, ne fait rien.
    """
    if settings.TESTING:
        return
    username = os.environ.get('DJANGO_SUPERUSER_USERNAME', '').strip()
    password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
    email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '').strip()
    if not username or not password:
        return

    User = apps.get_model('userManagement', 'CustomUser')
    Group = apps.get_model('auth', 'Group')
    if User.objects.filter(username=username).exists():
        return
    user = User.objects.create(
        username=username,
        email=email,
        password=make_password(password),
        is_staff=True,
        is_superuser=True,
    )
    # Les groupes de rôles sont créés en post_migrate, donc pas encore présents ici.
    group, _ = Group.objects.get_or_create(name='admin')
    user.groups.add(group)


class Migration(migrations.Migration):

    dependencies = [
        ('userManagement', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_initial_admin, migrations.RunPython.noop),
    ]
