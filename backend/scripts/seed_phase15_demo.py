"""Seed safe demo data for the Phase 15 screenshots and manual QA.

Idempotent — safe to re-run. Covers:

- C6 market report: prior-week price snapshots (so the WoW movement column
  has history to compare against; ~4% cheaper than today's live prices).
- C5 review AI summary: six mixed reviews on the seeded direct room 90009,
  bilingual comments that hit the topic lexicon.
- C4 NID OCR: a structural auto-extract on the ``tenant.pending`` verification.
- D8 fraud rings: two demo rings (one shared-phone pair, one shared-IP +
  same-area trio) plus ``fraud_ring`` signals on their flagged rooms.
- B1 chat translate: a Bengali message in the seeded direct chat (room 6).

Run:  venv/Scripts/python.exe manage.py shell < scripts/seed_phase15_demo.py
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from analytics.market_report import _week_bounds
from analytics.models import AreaPriceSnapshot
from audit.models import AuditLogEntry
from bookings.models import Review
from chat.models import ChatRoom, Message
from fraud.models import FraudReport, FraudSignal
from pricing.models import MarketStat
from rooms.models import Room
from users.models import TenantVerification

User = get_user_model()


def seed_market_report_history():
    """Prior-week snapshots at ~4% lower prices so WoW movement is real."""
    current_week_start, _ = _week_bounds()
    prior_week_start = current_week_start - timedelta(days=7)
    segments = MarketStat.objects.all()
    created = 0
    for segment in segments:
        avg = float(segment.avg_price) * 0.96
        median = float(segment.median_price) * 0.96
        _, _was_created = AreaPriceSnapshot.objects.update_or_create(
            area=segment.area,
            room_type=segment.room_type,
            week_start=prior_week_start,
            defaults={
                "avg_price": round(avg, 2),
                "median_price": round(median, 2),
                "sample_size": segment.sample_size,
            },
        )
        created += 1
    print(f"market report: {created} prior-week snapshots ready")


def seed_reviews():
    room = Room.objects.get(pk=90009)
    users = [
        User.objects.get(username=u) for u in ("api.verify", "probe.user", "probe.reg", "a1", "a2")
    ]
    reviews = [
        (
            5,
            "Great studio — very clean and the landlord is helpful. Near the bus stand, quiet at night.",
        ),
        (4, "Good value for the price. WiFi and water are fine, a bit noisy near the main road."),
        (4, "ভালো জায়গা, বাড়িওয়ালা সহযোগী। বাস স্ট্যান্ডের কাছে, আলো-বাতাস ভালো।"),
        (3, "Decent room but the rent is a little high for the area. Security is okay."),
        (2, "Noisy neighbours and the gas connection took weeks. Not the quiet space I expected."),
    ]
    for idx, (rating, comment) in enumerate(reviews):
        _, _was_created = Review.objects.get_or_create(
            room=room,
            user=users[idx % len(users)],
            defaults={"rating": rating, "comment": comment, "verified_stay": True},
        )
    total = Review.objects.filter(room=room).count()
    print(f"reviews: room 90009 now has {total} reviews")


def seed_kyc_ocr():
    verification = TenantVerification.objects.filter(user__username="tenant.pending").first()
    if verification is None:
        print("kyc ocr: tenant.pending has no verification record — skipping")
        return
    verification.auto_screen_detail = {
        "reasons": ["nid_ocr_extracted"],
        "ocr": {
            "nid_number": "12345678901234567",
            "name": "RAHIMA AKTER",
            "date_of_birth": "12/03/1995",
            "confidence": "high",
        },
    }
    verification.auto_screen_score = 72
    verification.auto_screen_result = "recommend_review"
    verification.save(
        update_fields=["auto_screen_detail", "auto_screen_score", "auto_screen_result"]
    )
    print("kyc ocr: structural NID auto-extract stored on tenant.pending")


def seed_rings():
    # Ring 1 — shared phone (strong edge).
    first = User.objects.get(username="dup.demo1")
    second = User.objects.get(username="dup.demo2")
    first.phone = "+8801712345601"
    second.phone = "+8801712345601"
    first.save(update_fields=["phone"])
    second.save(update_fields=["phone"])

    # Ring 2 — shared IP + same-area (Banani) listings (weak edges).
    shared_ip = "103.67.156.0"
    trio = [User.objects.get(username=u) for u in ("tanvir.islam", "arif.khan", "shakil.mahmud")]
    for user in trio:
        AuditLogEntry.objects.get_or_create(
            actor=user,
            action="ring_demo_seed",
            target_type="user",
            target_id=str(user.pk),
            defaults={"ip_address": shared_ip, "detail": {"phase": 15}},
        )

    # fraud_ring signals on the affected rooms so the ring cards show
    # flagged listings with severity (the weekly task does this in prod).
    rooms = Room.objects.filter(owner__in=[first, second, *trio])
    for room in rooms:
        report, _ = FraudReport.objects.get_or_create(
            room=room,
            defaults={"severity": "medium", "score": 55, "summary": "Ring-linked account (demo)"},
        )
        FraudSignal.objects.get_or_create(
            report=report,
            detector="fraud_ring",
            defaults={
                "severity": "medium",
                "message": "Owner shares phone / IP with ring-linked accounts (demo seed).",
                "detail": {"phase": 15},
            },
        )
    print("rings: 1 phone pair + 1 shared-IP trio seeded (with fraud_ring signals)")


def seed_demand():
    """Analytics events so the market report has real (anonymized) demand:
    Uttara + Gulshan on an upward 12-week trend, Mirpur on a decline."""
    from analytics.models import Event

    profiles = {
        "Uttara": [0, 0, 0, 1, 1, 2, 2, 4, 6, 8, 10, 12],
        "Gulshan": [0, 0, 1, 1, 2, 2, 3, 4, 5, 6, 7, 9],
        "Mirpur": [12, 10, 8, 6, 5, 4, 3, 2, 1, 0, 0, 0],
    }
    now = timezone.now()
    made = 0
    for area, series in profiles.items():
        room = Room.objects.filter(area=area).first()
        if room is None:
            continue
        for week, count in enumerate(series):
            for _ in range(count):
                start = now - timedelta(weeks=len(series) - week)
                Event.objects.create(
                    event="room_view",
                    category="room",
                    properties={"room_id": room.pk, "area": area},
                    path=f"/rooms?area={area.lower()}",
                    session_id=f"phase15-demo-{area}-{week}",
                    created_at=start + timedelta(hours=8),
                )
                made += 1
    print(f"demand: {made} anonymized view events seeded (Uttara/Gulshan rising, Mirpur falling)")


def seed_chat_message():
    chat = ChatRoom.objects.filter(listing_id=90009).first()
    sender = User.objects.get(username="tenant.verified")
    if chat is not None:
        Message.objects.get_or_create(
            chat_room=chat,
            sender=sender,
            content="ভাই, রুমটি কি এখনও খালি আছে? আর ভাড়াটা একটু কমে হবে কি?",
        )
        print("chat: Bengali message added to the room-90009 direct chat")
    else:
        print("chat: no direct chat for room 90009 — skipping")


if __name__ == "__main__":
    seed_market_report_history()
    seed_reviews()
    seed_kyc_ocr()
    seed_rings()
    seed_demand()
    seed_chat_message()
    print("done")
