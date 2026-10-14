from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Donne (ou retire avec --remove) les droits de super-admin (superutilisateur) à un compte existant."

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('--remove', action='store_true', help="Retire les droits de super-admin.")

    def handle(self, username, remove=False, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            raise CommandError(f"Aucun compte « {username} ».")
        if remove and User.objects.filter(is_superuser=True).exclude(pk=user.pk).count() == 0:
            raise CommandError("C'est le dernier super-admin : nommez-en un autre avant de lui retirer ses droits.")
        user.is_superuser = user.is_staff = not remove
        user.save(update_fields=['is_superuser', 'is_staff'])
        self.stdout.write(self.style.SUCCESS(
            f"{user.username} {'n’est plus' if remove else 'est maintenant'} super-admin."
        ))
