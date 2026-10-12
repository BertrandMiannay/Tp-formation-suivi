import os
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Copie à chaud de la base SQLite (API de sauvegarde SQLite, cohérente même pendant des écritures) "
        "dans BACKUP_DIR (par défaut <dossier de la base>/backups), en ne gardant que les --keep plus récentes "
        "de même étiquette."
    )

    def add_arguments(self, parser):
        parser.add_argument('--label', default='quotidienne', help="Étiquette ajoutée au nom du fichier.")
        parser.add_argument('--keep', type=int, default=14, help="Nombre de copies conservées pour cette étiquette.")
        parser.add_argument('--dir', help="Dossier de destination (sinon BACKUP_DIR).")

    def handle(self, *args, label, keep, dir, **options):
        db = settings.DATABASES['default']
        if db['ENGINE'] != 'django.db.backends.sqlite3':
            raise CommandError("backup_db ne gère que SQLite (utiliser l'outil de sauvegarde du serveur de base).")
        source = Path(db['NAME'])
        # Base absente ou vide (premier démarrage) : rien à sauvegarder.
        if not source.exists() or source.stat().st_size == 0:
            self.stdout.write(f"Pas de base à sauvegarder ({source}).")
            return
        if not label.replace('-', '').isalnum():
            raise CommandError("L'étiquette ne doit contenir que des lettres, chiffres et tirets.")

        target_dir = Path(dir or os.environ.get('BACKUP_DIR') or source.parent / 'backups')
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"db-{datetime.now():%Y%m%d-%H%M%S}-{label}.sqlite3"

        src = sqlite3.connect(source)
        dst = sqlite3.connect(target)
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
            src.close()
        self.stdout.write(f"Sauvegarde : {target}")

        # Rotation : seules les `keep` copies les plus récentes de cette étiquette sont conservées.
        copies = sorted(target_dir.glob(f"db-*-{label}.sqlite3"), reverse=True)
        for old in copies[max(keep, 1):]:
            old.unlink()
            self.stdout.write(f"Supprimée : {old.name}")
