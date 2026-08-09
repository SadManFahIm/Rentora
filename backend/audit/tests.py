"""Tests for the audit-log app."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLogEntry
from audit.services import log_action
from fraud.services.detectors import run_scan
from rooms.models import Room

User = get_user_model()


def make_user(username, **kwargs):
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password="test12345", **kwargs
    )


def make_room(owner, title="Cozy Single, Mirpur"):
    return Room.objects.create(
        owner=owner,
        title=title,
        description="Nice room.",
        room_type="single",
        price=8000,
        area="Mirpur",
        address="12 Mirpur Road",
        lat=23.8069,
        lng=90.3687,
        amenities=["wifi"],
        size_sqft=250,
    )


class AuditModelTests(TestCase):
    def test_log_action_records_actor_and_target(self):
        user = make_user("alice")
        room = make_room(user)
        entry = log_action(actor=user, action="test.action", target=room, detail={"x": 1})

        self.assertEqual(entry.actor, user)
        self.assertEqual(entry.target_type, "rooms.Room")
        self.assertEqual(entry.target_id, str(room.pk))
        self.assertEqual(entry.detail, {"x": 1})

    def test_log_action_allows_system_actor(self):
        entry = log_action(action="system.tick")
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.action, "system.tick")

    def test_log_action_never_raises_for_bad_request(self):
        # No request, no target, no actor — still writes a row.
        entry = log_action(action="orphan")
        self.assertIsNotNone(entry.pk)


class AuditFraudReviewTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", email="boss@example.com", password="x", is_staff=True
        )
        self.owner = make_user("owner")
        self.room = make_room(self.owner)
        self.report = run_scan(self.room)

    def test_fraud_review_writes_audit_entry(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f"/api/v1/fraud/reports/{self.report.pk}/review/", {"action": "dismissed"}
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        entry = AuditLogEntry.objects.filter(action="fraud.report.dismissed").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.target_id, str(self.report.pk))
        self.assertEqual(entry.detail, {"room_id": self.room.pk})

    def test_non_admin_review_writes_no_audit_entry(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(
            f"/api/v1/fraud/reports/{self.report.pk}/review/", {"action": "reviewed"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(AuditLogEntry.objects.count(), 0)
