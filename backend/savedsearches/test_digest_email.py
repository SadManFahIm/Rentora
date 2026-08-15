"""Tier-1 quick win — daily saved-search **email** digest.

The digest is complementary to the in-app matcher: it tracks its own cursor
(``SavedSearch.digest_sent_at``), sends exactly one branded email per user
with new hard-filter matches (deduped across their saved searches), respects
the per-account opt-out, and never emails a user about their own listing.
Delivery runs through ``send_alert_email`` so the daily budget + backoff
guards and the delivery ledger apply (covered by notifications tests).
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase

from rooms.models import Room
from savedsearches.models import SavedSearch
from savedsearches.tasks import send_saved_search_digests

User = get_user_model()


class SavedSearchEmailDigestTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="digest_user", email="digest@example.com", password="test12345"
        )
        self.landlord = User.objects.create_user(
            username="digest_owner", email="digest_owner@example.com", password="test12345"
        )

    def _room(self, title="Uttara Room", area="Uttara", price=10000):
        return Room.objects.create(
            owner=self.landlord,
            title=title,
            description="A cozy room near university.",
            room_type="single",
            price=price,
            area=area,
            address="12 Road",
            lat=23.8,
            lng=90.4,
            amenities=["wifi"],
            size_sqft=250,
        )

    def _save(self, user=None, name="Uttara rooms", **filters):
        return SavedSearch.objects.create(user=user or self.user, name=name, filters=filters)

    def test_digest_emails_new_matches_once(self):
        room = self._room()
        self._save(area="Uttara")

        result = send_saved_search_digests()
        self.assertEqual(result["users"], 1)
        self.assertEqual(result["emailed"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(room.title, mail.outbox[0].body)
        self.assertIn("Uttara", mail.outbox[0].body)

        # Cursor advanced: the same room is not emailed again.
        result2 = send_saved_search_digests()
        self.assertEqual(result2["emailed"], 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_one_email_per_user_deduped_across_searches(self):
        self._room(title="Room A", area="Uttara")
        self._room(title="Room B", area="Mirpur")
        self._save(name="Uttara search", area="Uttara")
        self._save(name="Mirpur search", area="Mirpur")

        result = send_saved_search_digests()
        self.assertEqual(result["users"], 1)
        self.assertEqual(result["emailed"], 1)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("Room A", body)
        self.assertIn("Room B", body)

    def test_same_room_matching_two_searches_emailed_once(self):
        self._room(title="Shared Room", area="Uttara")
        self._save(name="Area search", area="Uttara")
        self._save(name="Budget search", price_max=20000)

        result = send_saved_search_digests()
        self.assertEqual(result["emailed"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].body.count("Shared Room"), 1)

    def test_opt_out_skips_digest_email(self):
        self._room()
        self.user.digest_emails_enabled = False
        self.user.save(update_fields=["digest_emails_enabled"])
        self._save(area="Uttara")

        result = send_saved_search_digests()
        self.assertEqual(result["emailed"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_never_emails_about_own_listing(self):
        self._room()
        self._save(user=self.landlord, area="Uttara")

        result = send_saved_search_digests()
        self.assertEqual(result["emailed"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_user_skipped(self):
        self._room()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self._save(area="Uttara")

        result = send_saved_search_digests()
        self.assertEqual(result["emailed"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_hard_filters_gate_the_email(self):
        self._room(area="Uttara")
        self._save(area="Gulshan")

        result = send_saved_search_digests()
        self.assertEqual(result["emailed"], 0)
        self.assertEqual(len(mail.outbox), 0)
