from django.db import migrations

ROLES = ('admin', 'instructor', 'student')  # du plus élevé au plus faible


def memberships_from_groups(apps, schema_editor):
    """Les rôles globaux (groupes Django) deviennent des rôles dans le club par défaut : administrateur,
    encadrant ou élève (compte élève ou rattaché à une fiche). Un superutilisateur devient super-admin (accès
    à tous les clubs) et reste administrateur du club par défaut. Les groupes de rôles sont ensuite supprimés."""
    Club = apps.get_model('clubs', 'Club')
    Membership = apps.get_model('clubs', 'Membership')
    User = apps.get_model('userManagement', 'CustomUser')
    Member = apps.get_model('formation', 'Member')
    Group = apps.get_model('auth', 'Group')
    club = Club.objects.order_by('pk').first()
    if club is None:
        return
    student_ids = set(Member.objects.filter(user__isnull=False).values_list('user_id', flat=True))
    for user in User.objects.all():
        names = set(user.groups.values_list('name', flat=True))
        if user.is_superuser:
            names.add('admin')
        if user.pk in student_ids:
            names.add('student')
        role = next((r for r in ROLES if r in names), None)
        if role:
            Membership.objects.get_or_create(user=user, club=club, defaults={'role': role})
    Group.objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('clubs', '0003_membership'),
        ('formation', '0006_member_user_per_club'),
        ('userManagement', '0003_customuser_last_club'),
    ]

    operations = [
        migrations.RunPython(memberships_from_groups, migrations.RunPython.noop),
    ]
