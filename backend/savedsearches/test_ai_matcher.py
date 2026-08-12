"""Tests for the AI saved-search matcher (Phase 11+).

Covers: valid match scoring, hard-filter gating, price-drop alerts,
notification threshold gating, deduplication/cooldown, and event-task
integration with RoomPriceHistory.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from notifications.models import Notification
from rooms.models import Room, RoomPriceHistory

User = get_user_model()


def make_user(username):
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password="test12345"
    )


def attach_images(room, count=4):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    from rooms.models import RoomImage

    for i in range(count):
        buffer = BytesIO()
        Image.new("RGB", (64, 64), (128, 128, 128)).save(buffer, format="PNG")
        RoomImage.objects.create(
            room=room,
            is_primary=(i == 0),
            image=SimpleUploadedFile(f"m{i}.png", buffer.getvalue(), "image/png"),
        )


def make_room(owner, **overrides):
    fields = dict(
        title="Complete Mirpur Flat",
        description=(
            "A complete 2-bedroom flat in Mirpur 10. Fully furnished with a study "
            "desk, wardrobe and bed. Attached bathroom, kitchen with gas and "
            "electricity, and high-speed wifi. 5 minutes walk from Mirpur 10 bus "
            "stand and the metro station. Available for immediate move-in."
        ),
        room_type="single",
        price=10000,
        area="Mirpur",
        address="House 27, Road 5, Mirpur 10, Dhaka 1216",
        lat=23.806,
        lng=90.368,
        amenities=["wifi", "attached bathroom", "kitchen", "furnished", "gas", "electricity"],
        size_sqft=220,
    )
    fields.update(overrides)
    return Room.objects.create(owner=owner, **fields)


class SavedSearchMatcherTests(APITestCase):
    def setUp(self):
        self.tenant = make_user("tenant1")
        self.landlord = make_user("landlord1")
        self.room = make_room(self.landlord)
        attach_images(self.room, 4)
        from savedsearches.models import SavedSearch

        self.search = SavedSearch.objects.create(
            user=self.tenant,
            name="Mirpur rooms",
            filters={"area": "Mirpur", "price_max": 12000},
            last_checked_at=timezone.now() - timedelta(days=1),
        )

    def test_valid_match_scores_above_threshold(self):
        from savedsearches.services import score_saved_search_match

        result = score_saved_search_match(self.search, self.room)
        self.assertIsNotNone(result)
        self.assertIsNotNone(result["level"])
        self.assertGreaterEqual(result["score"], 0.75)
        self.assertTrue(any("area" in r.lower() for r in result["reasons"]))

    def test_hard_filter_mismatch_never_matches(self):
        from savedsearches.services import score_saved_search_match

        other_area = make_room(self.landlord, title="Dhanmondi Room", area="Dhanmondi")
        result = score_saved_search_match(self.search, other_area)
        self.assertIsNone(result)

    def test_price_over_budget_never_matches(self):
        from savedsearches.services import score_saved_search_match

        expensive = make_room(self.landlord, title="Pricey Room", price=30000)
        result = score_saved_search_match(self.search, expensive)
        self.assertIsNone(result)

    def test_low_quality_match_stays_below_threshold(self):
        from savedsearches.services import score_saved_search_match

        bare = make_room(
            self.landlord,
            title="Bare Mirpur Room",
            description="Room.",
            address="x",
            amenities=[],
        )
        result = score_saved_search_match(self.search, bare)
        # Hard filters pass, but the listing is too incomplete to be a
        # "highly relevant" alert — the matcher stays quiet.
        self.assertIsNotNone(result)
        self.assertIsNone(result["level"])

    def test_notify_only_above_threshold(self):
        from savedsearches.services import notify_saved_search_match, score_saved_search_match

        bare = make_room(
            self.landlord,
            title="Bare Mirpur Room",
            description="Room.",
            address="x",
            amenities=[],
        )
        result = score_saved_search_match(self.search, bare)
        created = notify_saved_search_match(self.search, bare, score_result=result)
        self.assertFalse(created)
        self.assertFalse(Notification.objects.filter(user=self.tenant).exists())

        created = notify_saved_search_match(
            self.search, self.room, score_result=None, price_drop=0.25
        )
        self.assertTrue(created)
        notification = Notification.objects.get(user=self.tenant)
        self.assertEqual(notification.notification_type, Notification.Type.SAVED_SEARCH_MATCH)
        self.assertIn("Price dropped", notification.title)
        self.assertEqual(notification.meta.get("room_id"), self.room.id)

    def test_price_drop_alert_from_history(self):
        from savedsearches.services import latest_price_drop, notify_saved_search_match

        RoomPriceHistory.objects.create(room=self.room, price=15000)
        RoomPriceHistory.objects.create(room=self.room, price=12000)
        drop = latest_price_drop(self.room)
        self.assertIsNotNone(drop)
        self.assertGreaterEqual(drop, 0.2)

        created = notify_saved_search_match(
            self.search, self.room, score_result=None, price_drop=drop
        )
        self.assertTrue(created)
        notification = Notification.objects.get(user=self.tenant)
        self.assertIn("20%", notification.message) or self.assertIn(
            "Price dropped", notification.message
        )

    def test_cooldown_prevents_duplicate_alerts(self):
        from savedsearches.services import notify_saved_search_match

        self.assertTrue(
            notify_saved_search_match(self.search, self.room, score_result=None, price_drop=0.25)
        )
        self.assertFalse(
            notify_saved_search_match(self.search, self.room, score_result=None, price_drop=0.25)
        )
        self.assertEqual(Notification.objects.filter(user=self.tenant).count(), 1)

    def test_event_task_alerts_on_create(self):
        from savedsearches.tasks import match_room_event

        result = match_room_event(self.room.id, created=True)
        self.assertEqual(result["notified"], 1)
        notification = Notification.objects.get(user=self.tenant)
        self.assertIn(self.room.title, notification.message)

    def test_event_task_no_alert_for_own_listing(self):
        from savedsearches.tasks import match_room_event

        own_room = make_room(self.tenant)  # tenant is the owner
        result = match_room_event(own_room.id, created=True)
        self.assertEqual(result["notified"], 0)
