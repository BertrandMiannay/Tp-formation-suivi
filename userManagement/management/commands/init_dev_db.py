import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Reset the dev database and run migrations. The superuser is created by the "
        "userManagement 0002 migration from DJANGO_SUPERUSER_* (default admin / admin)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--username")
        parser.add_argument("--email")
        parser.add_argument("--password")

    def handle(self, *args, **options):
        # Garde-fou : la commande efface la base, elle ne doit jamais tourner en production.
        if not settings.DEBUG:
            raise CommandError("init_dev_db efface la base : réservé au développement (DEBUG=True).")

        # 1. Superuser credentials: options, then environment (.env), then defaults
        defaults = {"username": "admin", "email": "admin@example.com", "password": "admin"}
        for field, default in defaults.items():
            var = f"DJANGO_SUPERUSER_{field.upper()}"
            os.environ[var] = options[field] or os.environ.get(var, "").strip() or default

        # 2. Delete the SQLite database
        db_path = settings.DATABASES["default"]["NAME"]
        if os.path.exists(db_path):
            os.remove(db_path)
            self.stdout.write(self.style.WARNING(f"Deleted {db_path}"))

        # 3. Run migrations (creates the superuser)
        self.stdout.write("Running migrations...")
        call_command("migrate", verbosity=1)

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Superuser created: {os.environ['DJANGO_SUPERUSER_USERNAME']}"
        ))
        self.stdout.write("Login at /accounts/login/")
