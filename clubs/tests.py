from datetime import date

from django.test import TestCase

from formation.models import Cursus, Formation, Member, Season
from suivi.models import TrainingSession

from .models import Club


class DefaultClubTestCase(TestCase):
    def test_default_club_created_by_migration(self):
        self.assertEqual(Club.objects.count(), 1)

    def test_new_objects_attached_to_default_club(self):
        club = Club.objects.get()
        cursus = Cursus.objects.create(name='N1', date=date(2026, 1, 1))
        objects = [
            cursus,
            Formation.objects.create(name='N1 2026', cursus=cursus),
            Season.objects.create(label='2025-2026'),
            Member.objects.create(first_name='Léa', last_name='Martin'),
            TrainingSession.objects.create(date=date(2026, 1, 8)),
        ]
        for obj in objects:
            self.assertEqual(obj.club, club)

    def test_default_club_recreated_if_missing(self):
        Club.objects.all().delete()
        member = Member.objects.create(first_name='Léa', last_name='Martin')
        self.assertEqual(Club.objects.get(), member.club)

    def test_deleting_club_deletes_its_data(self):
        club = Club.objects.get()
        cursus = Cursus.objects.create(name='N1', date=date(2026, 1, 1))
        Formation.objects.create(name='N1 2026', cursus=cursus)
        TrainingSession.objects.create(date=date(2026, 1, 8))
        club.delete()
        self.assertFalse(Cursus.objects.exists())
        self.assertFalse(Formation.objects.exists())
        self.assertFalse(TrainingSession.objects.exists())
