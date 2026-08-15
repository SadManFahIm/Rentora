"""Seed Phase 12 (Trust & Safety V2) demo data — idempotent.

Creates the tenants, bookings, disputes, moderation records, reports,
chat-safety events and chat rooms the Phase 12 screenshots (and manual QA)
rely on. Safe to re-run: every object is created via get_or_create-style
guards keyed on natural identifiers.

Run:  python manage.py runscript seed_phase12_demo   (django-extensions)
      python manage.py shell < scripts/seed_phase12_demo.py  (fallback)
"""

import datetime as dt

from django.contrib.auth import get_user_model

User = get_user_model()
PASSWORD = "demo12345"


def _user(
    username, role, tenant_verified=False, nid_verified=False, staff=False, first="", last=""
):
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": f"{username}@rentora.com",
            "role": role,
            "first_name": first,
            "last_name": last,
            "is_staff": staff,
            "nid_verified": nid_verified,
            "tenant_verified": tenant_verified,
        },
    )
    if created:
        user.set_password(PASSWORD)
        user.save()
    return user


def main():
    from bookings.models import Booking, Review
    from chat.models import ChatRoom, ChatRoomMembership, ChatSafetyEvent, Message, Report
    from disputes.models import Dispute, DisputeEvidence
    from moderation.models import ModerationStatus, PhotoModeration, ReviewModeration
    from rooms.models import Room, RoomImage

    # ---- Users ---------------------------------------------------------
    landlord = _user("rahim.hossain", "landlord", nid_verified=True, first="Rahim", last="Hossain")
    tenant_verified = _user(
        "tenant.verified", "tenant", tenant_verified=True, first="Nusrat", last="Jahan"
    )
    _user("tenant.pending", "tenant", first="Mehedi", last="Hasan")
    _user("tenant.new", "tenant", first="Farhan", last="Ahmed")

    # ---- Tenant KYC: one pending application (admin queue + Reviewing card),
    # ---- one brand-new tenant with no record (Start Verification form) -----
    from users.models import TenantVerification

    pending_tenant = User.objects.get(username="tenant.pending")
    TenantVerification.objects.get_or_create(
        user=pending_tenant,
        defaults={
            "status": TenantVerification.Status.PENDING,
            "doc_type": "nid",
        },
    )

    # ---- Approved booking + paid deposit (deposit-protection demo) -----
    room = Room.objects.filter(owner=landlord).first()
    if room is None:
        room = Room.objects.create(
            owner=landlord,
            title="Sunlit Studio, Mirpur",
            description="Bright, fully furnished studio near the metro.",
            room_type="studio",
            price=15000,
            area="Mirpur",
            address="12 Road 4",
            lat=23.8069,
            lng=90.3687,
            amenities=["wifi", "ac", "furnished"],
            size_sqft=320,
        )
    booking, _ = Booking.objects.get_or_create(
        room=room,
        tenant=tenant_verified,
        defaults={
            "status": Booking.Status.APPROVED,
            "check_in": dt.date(2026, 2, 1),
            "monthly_rent": 15000,
            "security_deposit_amount": 7500,
            "security_deposit_paid": True,
            "agreement_signed": True,
        },
    )

    # ---- Dispute + evidence -------------------------------------------
    dispute, _ = Dispute.objects.get_or_create(
        booking=booking,
        opened_by=tenant_verified,
        defaults={
            "category": Dispute.Category.DEPOSIT,
            "description": "Moved out on the 1st with the flat in good condition, but the deposit has not been returned.",
        },
    )
    if dispute.evidence.count() == 0:
        DisputeEvidence.objects.create(
            dispute=dispute,
            uploaded_by=tenant_verified,
            kind=DisputeEvidence.Kind.TEXT,
            content="The flat was clean and nothing was damaged — photos taken at move-out.",
        )
        DisputeEvidence.objects.create(
            dispute=dispute,
            uploaded_by=landlord,
            kind=DisputeEvidence.Kind.TEXT,
            content="One window blind was broken and the oven needed professional cleaning.",
        )

    # ---- Review + moderation (one held, one approved) ------------------
    held_review, _ = Review.objects.get_or_create(
        room=room,
        user=tenant_verified,
        defaults={
            "rating": 5,
            "comment": "Nice place! Contact me on whatsapp 01712345678 for the best rate outside the app.",
            "verified_stay": True,
        },
    )
    ReviewModeration.objects.get_or_create(
        review=held_review,
        defaults={
            "status": ModerationStatus.PENDING,
            "risk_score": 75,
            "signals": [
                {"key": "contact_info", "label": "Contains phone number"},
                {"key": "spam_phrase", "label": "Spam-like phrasing"},
            ],
        },
    )

    # ---- Flagged listing photo (duplicate-image evidence) --------------
    image = RoomImage.objects.filter(room=room).first()
    if image is not None:
        PhotoModeration.objects.get_or_create(
            image=image,
            defaults={
                "target_type": PhotoModeration.TargetType.LISTING,
                "room": room,
                "image_url": image.image.url,
                "uploaded_by": landlord,
                "status": ModerationStatus.PENDING,
                "risk_score": 40,
                "signals": [
                    {
                        "key": "duplicate_image",
                        "label": "Visually similar to another listing's photo",
                        "matches": [{"room_id": 1, "title": "Modern Studio, Dhanmondi"}],
                    }
                ],
            },
        )

    # ---- Chat room: landlord <-> verified tenant + safety events -------
    chat, _ = ChatRoom.objects.get_or_create(room_type=ChatRoom.RoomType.DIRECT, listing=room)
    for member in (landlord, tenant_verified):
        ChatRoomMembership.objects.get_or_create(chat_room=chat, user=member)

    seeded_msgs = {
        "Hi! Is the studio still available from next month?": tenant_verified,
        "Yes — would you like to schedule a visit?": landlord,
        "Sure! Can you share the address?": tenant_verified,
    }
    for content, sender in seeded_msgs.items():
        Message.objects.get_or_create(
            chat_room=chat,
            sender=sender,
            content=content,
            message_type=Message.MessageType.TEXT,
        )

    if not ChatSafetyEvent.objects.exists():
        sender = landlord
        msg = Message.objects.filter(chat_room=chat).order_by("created_at").last()
        ChatSafetyEvent.objects.create(
            chat_room=chat,
            sender=sender,
            message=msg,
            risk_level=ChatSafetyEvent.RiskLevel.MEDIUM,
            outcome=ChatSafetyEvent.Outcome.WARNED,
            detectors=[{"key": "contact_redirect", "label": "External contact info"}],
            detail={"matched": ["bkash"]},
        )
        ChatSafetyEvent.objects.create(
            chat_room=chat,
            sender=sender,
            risk_level=ChatSafetyEvent.RiskLevel.HIGH,
            outcome=ChatSafetyEvent.Outcome.FLAGGED,
            detectors=[{"key": "payment_redirect", "label": "Payment request"}],
            detail={"matched": ["send money"]},
        )
        ChatSafetyEvent.objects.create(
            chat_room=chat,
            sender=sender,
            risk_level=ChatSafetyEvent.RiskLevel.CRITICAL,
            outcome=ChatSafetyEvent.Outcome.BLOCKED,
            detectors=[
                {"key": "payment_redirect", "label": "Payment request"},
                {"key": "impersonation", "label": "Impersonation of Rentora / staff"},
            ],
            detail={"matched": ["bkash", "outside the app"]},
        )

    # ---- Reports (admin moderation queue) ------------------------------
    Report.objects.get_or_create(
        reporter=tenant_verified,
        target_user=landlord,
        category=Report.Category.PAYMENT_FRAUD,
        defaults={
            "description": "Asked me to send the advance to a bKash number outside the app.",
        },
    )
    Report.objects.get_or_create(
        reporter=landlord,
        target_user=tenant_verified,
        category=Report.Category.OTHER,
        defaults={
            "description": "Repeated same-day booking requests after the first was accepted.",
        },
    )

    print(
        f"Phase 12 demo seeded: booking #{booking.pk}, dispute #{dispute.pk}, "
        f"review #{held_review.pk}, chat #{chat.pk}, "
        f"reports={Report.objects.count()}, safety events={ChatSafetyEvent.objects.count()}"
    )


if __name__ == "__main__":
    import os

    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    django.setup()
    main()
