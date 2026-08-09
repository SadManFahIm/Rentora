"""Shared business logic for the rooms app.

Single source of truth for behaviour that is reachable both from management
commands and from Celery tasks — so a scheduled run and a manual run can
never drift apart (e.g. the beat job forgetting to email owners).
"""

from __future__ import annotations

from rooms.models import Room


def expire_listing_tiers() -> dict[str, int]:
    """Revert expired Featured/Premium tiers to Free and email their owners.

    Returns ``{"expired": n}``. Emails are best-effort (fail_silently) — the
    tier rollback is the source of truth and happens regardless.
    """
    from django.utils import timezone

    from notifications.emails import send_html_email

    now = timezone.now()
    expired = list(
        Room.objects.filter(tier__in=[Room.Tier.FEATURED, Room.Tier.PREMIUM])
        .filter(tier_expires_at__lte=now)
        .select_related("owner")
    )

    for room in expired:
        if room.owner and room.owner.email:
            send_html_email(
                subject=f"Rentora: '{room.title}' promotion has ended",
                to_email=room.owner.email,
                template_name="promotion_expired",
                context={
                    "user": room.owner,
                    "room": room,
                    "tier_display": room.get_tier_display(),
                    "action_url": "/dashboard/listings",
                },
            )

    count = Room.objects.filter(pk__in=[room.pk for room in expired]).update(
        tier=Room.Tier.FREE,
        tier_expires_at=None,
        is_featured=False,
        updated_at=now,
    )
    return {"expired": count}
