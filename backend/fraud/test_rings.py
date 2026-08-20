"""Phase 15 (D8) — fraud ring detection.

Covers the graph engine (shared phones → strong edges, shared audit IP +
same-area listings → weak edges), the honesty rules (shared IP alone is not a
ring; phone normalization unifies +880/0 forms), the per-room ``fraud_ring``
detector inside the normal scan pipeline, the weekly task, and the admin-only
endpoint.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLogEntry
from fraud.models import FraudReport, FraudSignal
from fraud.services.detectors import run_scan
from fraud.services.rings import detect_rings, owner_ring_membership
from rooms.models import Room

User = get_user_model()


def make_room(owner, area="Uttara", title="Ring room"):
    return Room.objects.create(
        owner=owner,
        title=title,
        description="A test room.",
        room_type="single",
        price=12000,
        area=area,
        address="Road 1",
        lat=23.8759,
        lng=90.3795,
        amenities=["wifi"],
        size_sqft=250,
    )


def make_audit(actor, ip):
    return AuditLogEntry.objects.create(
        actor=actor,
        action="fraud.report.reviewed",
        target_type="fraud.FraudReport",
        target_id="1",
        ip_address=ip,
    )


class RingGraphTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(
            username="ring_a", email="ring_a@example.com", password="test12345"
        )
        self.b = User.objects.create_user(
            username="ring_b", email="ring_b@example.com", password="test12345"
        )
        self.c = User.objects.create_user(
            username="ring_c", email="ring_c@example.com", password="test12345"
        )

    def test_no_shared_data_yields_no_rings(self):
        make_room(self.a, "Uttara")
        make_room(self.b, "Mirpur")
        out = detect_rings()
        self.assertEqual(out["ring_count"], 0)

    def test_shared_phone_forms_strong_ring(self):
        self.a.phone = "01712345678"
        self.a.save(update_fields=["phone"])
        self.b.phone = "+880 1712 345678"
        self.b.save(update_fields=["phone"])
        make_room(self.a, "Uttara")
        make_room(self.b, "Uttara")

        out = detect_rings()
        self.assertEqual(out["ring_count"], 1)
        ring = out["rings"][0]
        self.assertEqual(ring["member_count"], 2)
        self.assertEqual(ring["strong_edges"], 1)
        self.assertEqual({m["user_id"] for m in ring["members"]}, {self.a.pk, self.b.pk})

    def test_phone_normalization_unifies_formats(self):
        # +880 1712 345678 vs 01712345678 (leading-zero form) must match.
        self.a.phone = "+8801712345678"
        self.a.save(update_fields=["phone"])
        self.b.phone = "01712345678"
        self.b.save(update_fields=["phone"])
        make_room(self.a, "Uttara")
        make_room(self.b, "Uttara")
        self.assertEqual(detect_rings()["ring_count"], 1)

    def test_shared_ip_alone_is_not_a_ring(self):
        make_audit(self.a, "203.0.113.10")
        make_audit(self.b, "203.0.113.10")
        make_room(self.a, "Uttara")
        make_room(self.b, "Mirpur")  # different areas → no coordination signal
        self.assertEqual(detect_rings()["ring_count"], 0)

    def test_shared_ip_plus_same_area_forms_weak_ring(self):
        make_audit(self.a, "203.0.113.10")
        make_audit(self.b, "203.0.113.10")
        make_room(self.a, "Uttara")
        make_room(self.b, "Uttara")
        out = detect_rings()
        self.assertEqual(out["ring_count"], 1)
        ring = out["rings"][0]
        self.assertEqual(ring["weak_edges"], 1)
        self.assertEqual(ring["strong_edges"], 0)
        # Weak-only rings score lower than phone-linked ones.
        self.assertLess(ring["score"], 100)

    def test_phone_edge_beats_weak_edge_for_pair(self):
        self.a.phone = "01712345678"
        self.a.save(update_fields=["phone"])
        self.b.phone = "01712345678"
        self.b.save(update_fields=["phone"])
        make_audit(self.a, "203.0.113.10")
        make_audit(self.b, "203.0.113.10")
        make_room(self.a, "Uttara")
        make_room(self.b, "Uttara")
        ring = detect_rings()["rings"][0]
        self.assertEqual(ring["strong_edges"], 1)
        self.assertEqual(ring["weak_edges"], 0)  # pair not double-counted

    def test_three_member_chain_counts_all(self):
        self.a.phone = "01712345678"
        self.a.save(update_fields=["phone"])
        self.b.phone = "01712345678"
        self.b.save(update_fields=["phone"])
        self.c.phone = "01798765432"
        self.c.save(update_fields=["phone"])
        make_room(self.a, "Uttara")
        make_room(self.b, "Uttara")
        make_room(self.c, "Mirpur")
        make_audit(self.b, "203.0.113.10")
        make_audit(self.c, "203.0.113.10")
        make_room(self.b, "Dhanmondi")
        make_room(self.c, "Dhanmondi")  # B-C also linked weak → one component
        out = detect_rings()
        self.assertEqual(out["ring_count"], 1)
        self.assertEqual(out["rings"][0]["member_count"], 3)


class RingDetectorTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(
            username="det_a", email="det_a@example.com", password="test12345"
        )
        self.b = User.objects.create_user(
            username="det_b", email="det_b@example.com", password="test12345"
        )

    def test_scan_attaches_medium_fraud_ring_signal(self):
        self.a.phone = "01712345678"
        self.a.save(update_fields=["phone"])
        self.b.phone = "01712345678"
        self.b.save(update_fields=["phone"])
        room_a = make_room(self.a, "Uttara")
        make_room(self.b, "Uttara")

        report = run_scan(room_a)
        ring_signal = report.signals.filter(detector=FraudSignal.Detector.FRAUD_RING).first()
        self.assertIsNotNone(ring_signal)
        self.assertEqual(ring_signal.severity, FraudReport.Severity.MEDIUM)
        self.assertEqual(ring_signal.detail["strength"], "strong")
        self.assertIn(self.b.pk, ring_signal.detail["peer_user_ids"])

    def test_weak_only_owner_gets_low_signal(self):
        make_audit(self.a, "203.0.113.10")
        make_audit(self.b, "203.0.113.10")
        room_a = make_room(self.a, "Uttara")
        make_room(self.b, "Uttara")

        report = run_scan(room_a)
        ring_signal = report.signals.filter(detector=FraudSignal.Detector.FRAUD_RING).first()
        self.assertIsNotNone(ring_signal)
        self.assertEqual(ring_signal.severity, FraudReport.Severity.LOW)

    def test_isolated_owner_gets_no_ring_signal(self):
        room = make_room(self.a, "Uttara")
        report = run_scan(room)
        self.assertFalse(report.signals.filter(detector=FraudSignal.Detector.FRAUD_RING).exists())

    def test_owner_ring_membership_focused_check(self):
        self.a.phone = "01712345678"
        self.a.save(update_fields=["phone"])
        self.b.phone = "01712345678"
        self.b.save(update_fields=["phone"])
        membership = owner_ring_membership(self.a)
        self.assertIsNotNone(membership)
        self.assertEqual(membership["strength"], "strong")
        # A user with no listings/phone/IP history is not a member of anything.
        isolated = User.objects.create_user(
            username="det_isolated", email="det_isolated@example.com", password="test12345"
        )
        self.assertIsNone(owner_ring_membership(isolated))
        self.assertIsNone(owner_ring_membership(None))


class RingTaskAndEndpointTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="ring_admin",
            email="ring_admin@example.com",
            password="test12345",
            is_staff=True,
        )
        self.a = User.objects.create_user(
            username="t_a", email="t_a@example.com", password="test12345"
        )
        self.b = User.objects.create_user(
            username="t_b", email="t_b@example.com", password="test12345"
        )
        self.a.phone = "01712345678"
        self.a.save(update_fields=["phone"])
        self.b.phone = "01712345678"
        self.b.save(update_fields=["phone"])

    def test_task_rescans_ring_member_rooms(self):
        room_a = make_room(self.a, "Uttara")
        make_room(self.b, "Uttara")

        from fraud.tasks import detect_rings

        result = detect_rings()
        self.assertEqual(result["ring_count"], 1)
        self.assertGreaterEqual(result["re_scanned"], 1)
        report = FraudReport.objects.get(room=room_a)
        self.assertTrue(report.signals.filter(detector=FraudSignal.Detector.FRAUD_RING).exists())

    def test_endpoint_admin_only(self):
        url = "/api/v1/fraud/rings/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(self.a)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("rings", resp.data)
        self.assertIn("note", resp.data)

    def test_flagged_rooms_surface_in_ring(self):
        room_a = make_room(self.a, "Uttara")
        make_room(self.b, "Uttara")
        run_scan(room_a)  # owner in a ring → flagged report
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/v1/fraud/rings/")
        ring = resp.data["rings"][0]
        self.assertTrue(any(r["room_id"] == room_a.pk for r in ring["flagged_rooms"]))
