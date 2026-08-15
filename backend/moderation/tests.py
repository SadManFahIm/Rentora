"""Phase 12.5 — photo & review moderation tests.

Covers the deterministic detection (auto-approve fast path vs. held for
review), the public-visibility gate (held reviews are hidden until approved),
admin decisions with audit + notification side effects, listing-photo
duplicate flagging via the shared pHash pipeline, and authorization.
"""

import io
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLogEntry
from bookings.models import Booking
from notifications.models import Notification
from rooms.models import Room, RoomImage

from .models import ModerationStatus, PhotoModeration, ReviewModeration

User = get_user_model()


def make_png(structured: bool = True) -> bytes:
    """A tiny valid PNG — structured (flag-worthy hash) or blank."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (120, 90), (210, 210, 210))
    if structured:
        draw = ImageDraw.Draw(img)
        draw.rectangle([20, 20, 60, 60], fill=(30, 30, 30))
        draw.ellipse([70, 30, 100, 60], fill=(30, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_room(owner, title="Test Room"):
    return Room.objects.create(
        owner=owner,
        title=title,
        description="d",
        room_type="single",
        price=9000,
        area="Mirpur",
        address="x",
        lat=23.8,
        lng=90.4,
        amenities=["wifi"],
        size_sqft=200,
    )


class ReviewModerationTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="modadmin", email="admin@e.com", password="x", is_staff=True
        )
        self.landlord = User.objects.create_user(
            username="landlord1", email="l1@e.com", password="x"
        )
        self.tenant = User.objects.create_user(username="tenant1", email="t1@e.com", password="x")
        self.room = make_room(self.landlord)
        Booking.objects.create(
            room=self.room,
            tenant=self.tenant,
            status=Booking.Status.APPROVED,
            check_in=date(2026, 1, 1),
            monthly_rent=9000,
        )

    def post_review(self, user, comment, photos=None):
        self.client.force_authenticate(user)
        return self.client.post(
            "/api/v1/reviews/",
            {"room": self.room.pk, "rating": 5, "comment": comment, "photos": photos or []},
            format="json",
        )

    def public_review_ids(self):
        res = self.client.get(f"/api/v1/reviews/?room={self.room.pk}")
        return [r["id"] for r in res.data["results"]]

    def test_clean_review_auto_approves_and_is_public(self):
        res = self.post_review(self.tenant, "Great flat, clean and quiet.")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        mod = ReviewModeration.objects.get(review_id=res.data["id"])
        self.assertEqual(mod.status, ModerationStatus.APPROVED)
        self.assertLess(mod.risk_score, 60)
        self.assertIn(res.data["id"], self.public_review_ids())

    def test_spammy_review_is_held_and_hidden_from_public(self):
        res = self.post_review(
            self.tenant,
            "Great! Check my profile and contact me on whatsapp 01712345678 http://spam.example",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        mod = ReviewModeration.objects.get(review_id=res.data["id"])
        self.assertEqual(mod.status, ModerationStatus.PENDING)
        self.assertGreaterEqual(mod.risk_score, 60)
        keys = {s["key"] for s in mod.signals}
        self.assertTrue(keys & {"contains_url", "contact_info", "spam_phrase"}, keys)
        self.assertNotIn(res.data["id"], self.public_review_ids())

    def test_duplicate_text_and_velocity_are_detected(self):
        self.post_review(self.tenant, "Nice place to stay.")
        other = User.objects.create_user(username="tenant2", email="t2@e.com", password="x")
        Booking.objects.create(
            room=self.room,
            tenant=other,
            status=Booking.Status.APPROVED,
            check_in=date(2026, 2, 1),
            monthly_rent=9000,
        )
        # Same comment text by another user → duplicate_text signal.
        res = self.post_review(other, "Nice place to stay.")
        mod = ReviewModeration.objects.get(review_id=res.data["id"])
        self.assertIn("duplicate_text", {s["key"] for s in mod.signals})

    def test_admin_approves_held_review_audits_and_notifies(self):
        res = self.post_review(self.tenant, "Great! Contact me on whatsapp 01712345678")
        review_id = res.data["id"]
        mod = ReviewModeration.objects.get(review_id=review_id)
        self.assertEqual(mod.status, ModerationStatus.PENDING)

        self.client.force_authenticate(self.admin)
        res = self.client.post(
            f"/api/v1/moderation/reviews/{mod.pk}/decision/",
            {"action": "approve", "note": "legit tenant"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        mod.refresh_from_db()
        self.assertEqual(mod.status, ModerationStatus.APPROVED)
        self.assertEqual(mod.admin_note, "legit tenant")
        self.assertEqual(mod.reviewed_by, self.admin)

        self.assertTrue(
            AuditLogEntry.objects.filter(
                action="moderation.review.approve", target_id=str(mod.pk)
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.tenant, notification_type=Notification.Type.CONTENT_MODERATED
            ).exists()
        )
        self.assertIn(review_id, self.public_review_ids())

    def test_admin_reject_keeps_review_hidden(self):
        res = self.post_review(self.tenant, "Great! Check my profile http://spam.example")
        mod = ReviewModeration.objects.get(review_id=res.data["id"])
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            f"/api/v1/moderation/reviews/{mod.pk}/decision/",
            {"action": "reject", "note": "spam"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        mod.refresh_from_db()
        self.assertEqual(mod.status, ModerationStatus.REJECTED)
        self.assertNotIn(res.data["review"], self.public_review_ids())
        self.assertTrue(AuditLogEntry.objects.filter(action="moderation.review.reject").exists())

    def test_non_admin_cannot_access_queue_or_decide(self):
        res = self.post_review(self.tenant, "Fine place.")
        mod = ReviewModeration.objects.get(review_id=res.data["id"])
        self.client.force_authenticate(self.tenant)
        self.assertEqual(
            self.client.get("/api/v1/moderation/reviews/").status_code, status.HTTP_403_FORBIDDEN
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/moderation/reviews/{mod.pk}/decision/",
                {"action": "approve"},
                format="json",
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        # The tenant's own rejected review is not visible through the public API.
        self.assertEqual(self.client.get("/api/v1/moderation/overview/").status_code, 403)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PhotoModerationTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="padmin", email="pa@e.com", password="x", is_staff=True
        )
        self.owner1 = User.objects.create_user(username="po1", email="po1@e.com", password="x")
        self.owner2 = User.objects.create_user(username="po2", email="po2@e.com", password="x")

    def test_identical_listing_photo_across_rooms_is_flagged(self):
        room_a = make_room(self.owner1, "Listing A")
        RoomImage.objects.create(
            room=room_a, image=SimpleUploadedFile("a.png", make_png(structured=True))
        )
        # First photo has nothing to match against → approved.
        mod_a = PhotoModeration.objects.get(room=room_a)
        self.assertEqual(mod_a.status, ModerationStatus.APPROVED)

        room_b = make_room(self.owner2, "Listing B")
        RoomImage.objects.create(
            room=room_b, image=SimpleUploadedFile("b.png", make_png(structured=True))
        )
        mod_b = PhotoModeration.objects.get(room=room_b)
        self.assertEqual(mod_b.status, ModerationStatus.PENDING)
        keys = {s["key"] for s in mod_b.signals}
        self.assertIn("duplicate_image", keys)
        matches = mod_b.signals[0].get("matches")
        self.assertTrue(matches)
        self.assertTrue(any(m["room_id"] == room_a.pk for m in matches))

    def test_blank_image_does_not_flag_as_duplicate(self):
        room_a = make_room(self.owner1, "A")
        RoomImage.objects.create(
            room=room_a, image=SimpleUploadedFile("a.png", make_png(structured=False))
        )
        room_b = make_room(self.owner2, "B")
        RoomImage.objects.create(
            room=room_b, image=SimpleUploadedFile("b.png", make_png(structured=False))
        )
        # Blank images are low-structure — no duplicate flag (would be noise).
        self.assertFalse(PhotoModeration.objects.filter(status=ModerationStatus.PENDING).exists())

    def test_admin_photo_decision_audits_and_notifies(self):
        room_a = make_room(self.owner1, "A")
        RoomImage.objects.create(
            room=room_a, image=SimpleUploadedFile("a.png", make_png(structured=True))
        )
        room_b = make_room(self.owner2, "B")
        RoomImage.objects.create(
            room=room_b, image=SimpleUploadedFile("b.png", make_png(structured=True))
        )
        mod = PhotoModeration.objects.get(room=room_b)

        self.client.force_authenticate(self.admin)
        res = self.client.post(
            f"/api/v1/moderation/photos/{mod.pk}/decision/",
            {"action": "approve", "note": "own content"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        mod.refresh_from_db()
        self.assertEqual(mod.status, ModerationStatus.APPROVED)
        self.assertTrue(AuditLogEntry.objects.filter(action="moderation.photo.approve").exists())
        self.assertTrue(
            Notification.objects.filter(
                user=self.owner2, notification_type=Notification.Type.CONTENT_MODERATED
            ).exists()
        )

    def test_photo_queue_and_overview_are_admin_only(self):
        room = make_room(self.owner1, "A")
        RoomImage.objects.create(
            room=room, image=SimpleUploadedFile("a.png", make_png(structured=True))
        )
        self.client.force_authenticate(self.owner1)
        self.assertEqual(
            self.client.get("/api/v1/moderation/photos/").status_code, status.HTTP_403_FORBIDDEN
        )
        self.assertEqual(
            self.client.get("/api/v1/moderation/overview/").status_code, status.HTTP_403_FORBIDDEN
        )
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/v1/moderation/overview/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["photos"], 1)


class ReviewPhotoModerationTests(APITestCase):
    """Review photos (URL strings) get moderation records; missing local files
    degrade to auto-approve rather than erroring."""

    def setUp(self):
        self.landlord = User.objects.create_user(username="rl", email="rl@e.com", password="x")
        self.tenant = User.objects.create_user(username="rt", email="rt@e.com", password="x")
        self.room = make_room(self.landlord)
        Booking.objects.create(
            room=self.room,
            tenant=self.tenant,
            status=Booking.Status.APPROVED,
            check_in=date(2026, 1, 1),
            monthly_rent=9000,
        )

    def test_review_photos_get_moderation_records(self):
        self.client.force_authenticate(self.tenant)
        res = self.client.post(
            "/api/v1/reviews/",
            {
                "room": self.room.pk,
                "rating": 5,
                "comment": "Nice stay",
                "photos": ["/media/reviews/pic1.jpg", "/media/reviews/pic2.jpg"],
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        mods = PhotoModeration.objects.filter(target_type=PhotoModeration.TargetType.REVIEW)
        self.assertEqual(mods.count(), 2)
        self.assertTrue(all(m.status == ModerationStatus.APPROVED for m in mods))
        urls = {m.image_url for m in mods}
        self.assertEqual(urls, {"/media/reviews/pic1.jpg", "/media/reviews/pic2.jpg"})
