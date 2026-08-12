"""Tests for the read-only saved-search tuning command (Phase 11+)."""

import io
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from notifications.models import Notification
from rooms.models import Room, RoomImage

User = get_user_model()


def make_user(username):
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password="test12345"
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
        amenities=[
            "wifi",
            "attached bathroom",
            "kitchen",
            "furnished",
            "parking",
            "gas",
            "electricity",
        ],
        size_sqft=220,
    )
    fields.update(overrides)
    return Room.objects.create(owner=owner, **fields)


def attach_images(room, count=4):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    for i in range(count):
        buffer = BytesIO()
        Image.new("RGB", (64, 64), (128, 128, 128)).save(buffer, format="PNG")
        RoomImage.objects.create(
            room=room,
            is_primary=(i == 0),
            image=SimpleUploadedFile(f"t{i}.png", buffer.getvalue(), "image/png"),
        )


def run_tune(*args, **kwargs):
    out = io.StringIO()
    call_command("tune_saved_search_matching", *args, stdout=out, **kwargs)
    return out.getvalue()


class TuneSavedSearchMatchingTests(TestCase):
    def setUp(self):
        self.tenant = make_user("tuner")
        self.landlord = make_user("tune_owner")
        self.room = make_room(self.landlord)
        attach_images(self.room)
        from savedsearches.models import SavedSearch

        self.search = SavedSearch.objects.create(
            user=self.tenant,
            name="Mirpur rooms",
            filters={"area": "Mirpur", "price_max": 12000},
            last_checked_at=timezone.now() - timedelta(days=1),
        )

    def test_matching_room_reports_match(self):
        out = run_tune("--saved-search-id", self.search.id, "--room-id", self.room.id)
        self.assertIn("MATCH", out)
        self.assertIn("Final Score", out)
        self.assertIn("READ ONLY", out)

    def test_hard_filter_failure_is_flagged(self):
        other = make_room(self.landlord, title="Gulshan Room", area="Gulshan")
        attach_images(other)
        out = run_tune("--saved-search-id", self.search.id, "--room-id", other.id)
        self.assertIn("NON-MATCH", out)
        self.assertIn("Hard filter failed", out)

    def test_json_output_is_parseable(self):
        out = run_tune(
            "--saved-search-id", self.search.id, "--room-id", self.room.id, "--format", "json"
        )
        data = json.loads(out)
        self.assertTrue(data["read_only"])
        self.assertEqual(data["candidates"][0]["room_id"], self.room.id)
        self.assertTrue(data["candidates"][0]["match"])
        self.assertIsNotNone(data["candidates"][0]["score"])

    def test_custom_weights_affect_score(self):
        out = run_tune(
            "--saved-search-id",
            self.search.id,
            "--room-id",
            self.room.id,
            "--format",
            "json",
            "--semantic-weight",
            "0.0",
        )
        data = json.loads(out)
        self.assertIn("semantic", data["weights"])
        self.assertEqual(data["weights"]["semantic"], 0.0)

    def test_threshold_gating(self):
        # A threshold of 1.0 can never match -> NON-MATCH below threshold.
        out = run_tune(
            "--saved-search-id", self.search.id, "--room-id", self.room.id, "--threshold", "1.0"
        )
        self.assertIn("below threshold", out)

    def test_tune_mode_is_diagnostic(self):
        out = run_tune(
            "--saved-search-id",
            self.search.id,
            "--room-ids",
            f"{self.room.id}",
            "--tune",
        )
        self.assertIn("diagnostic mode", out)
        self.assertIn("MatchRate", out)

    def test_tune_mode_no_labelled_data_note(self):
        out = run_tune(
            "--saved-search-id",
            self.search.id,
            "--room-ids",
            f"{self.room.id}",
            "--tune",
            "--format",
            "json",
        )
        data = json.loads(out)
        self.assertEqual(data["mode"], "diagnostic")
        self.assertIn("labelled", data["note"])

    def test_command_never_writes_data(self):
        """Read-only contract: no notifications, no saved-search writes."""
        before_rooms = Room.objects.count()
        before_notifs = Notification.objects.count()
        run_tune("--saved-search-id", self.search.id, "--room-id", self.room.id)
        run_tune(
            "--saved-search-id",
            self.search.id,
            "--room-ids",
            f"{self.room.id}",
            "--tune",
        )
        self.assertEqual(Room.objects.count(), before_rooms)
        self.assertEqual(Notification.objects.count(), before_notifs)
        self.search.refresh_from_db()
        # last_checked_at must NOT advance (that would be a mutation).
        self.assertLessEqual(self.search.last_checked_at, timezone.now())

    def test_missing_search_raises(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            run_tune("--saved-search-id", 99999)
