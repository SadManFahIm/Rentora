"""Corporate services: RBAC helpers, bulk booking, invoicing."""

from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction

from bookings.models import Booking

from .models import CorporateAccount, CorporateInvoice, CorporateMember

User = get_user_model()


def _is_admin(user) -> bool:
    return user.is_staff or user.role == user.Role.ADMIN


def can_manage_account(user, account: CorporateAccount) -> bool:
    """Account-level admin: the owner, an ADMIN member, or a platform admin."""
    if _is_admin(user) or account.owner_id == user.id:
        return True
    return CorporateMember.objects.filter(
        account=account, user=user, role=CorporateMember.Role.ADMIN
    ).exists()


def is_member(user, account: CorporateAccount) -> bool:
    if _is_admin(user) or account.owner_id == user.id:
        return True
    return CorporateMember.objects.filter(account=account, user=user).exists()


def accounts_for(user):
    """Accounts the user owns, administers, or belongs to."""
    owned = CorporateAccount.objects.filter(owner=user)
    if _is_admin(user):
        return CorporateAccount.objects.all()
    member_ids = CorporateMember.objects.filter(user=user).values_list("account_id", flat=True)
    return owned | CorporateAccount.objects.filter(pk__in=list(member_ids))


def _derive_username(email: str) -> str:
    base = email.split("@")[0][:20] or "member"
    username = base
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base}{counter}"
        counter += 1
    return username


def _get_or_create_member_user(data: dict) -> User:
    email = (data.get("email") or "").strip().lower()
    user = User.objects.filter(email=email).first()
    if user is not None:
        return user
    username = _derive_username(email or "corporate-member")
    user = User.objects.create(
        username=username,
        email=email or "",
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
        phone=data.get("phone", ""),
        role=User.Role.TENANT,
    )
    user.set_unusable_password()
    user.save(update_fields=["password"])
    return user


def bulk_create_bookings(*, account, room, check_in, check_out, members, notes="") -> dict:
    """Create one PENDING booking per member (partial success).

    Mirrors ``rooms/views.py`` bulk-create: each row is validated
    independently and reported with its index on failure.
    """
    created = []
    errors = []
    for index, row in enumerate(members):
        try:
            with transaction.atomic():
                user = _get_or_create_member_user(row)
                booking = Booking.objects.create(
                    room=room,
                    tenant=user,
                    status=Booking.Status.PENDING,
                    check_in=check_in,
                    check_out=check_out,
                    monthly_rent=row.get("monthly_rent") or room.price,
                    notes=notes,
                    corporate_account=account,
                )
                created.append(booking.id)
        except Exception as exc:
            errors.append({"index": index, "errors": str(exc)})
    return {"created": created, "created_count": len(created), "errors": errors}


def next_invoice_number() -> str:
    year = date.today().year
    seq = CorporateInvoice.objects.count() + 1
    return f"CORP-{year}-{seq:04d}"


def generate_invoice(
    account: CorporateAccount, period_start: date, period_end: date
) -> CorporateInvoice:
    """Create (or return the existing) invoice for a corporate period.

    Idempotent by (account, period). Amount = sum of approved corporate
    bookings' monthly rent active within the period.
    """
    existing = CorporateInvoice.objects.filter(
        account=account, period_start=period_start, period_end=period_end
    ).first()
    if existing is not None:
        return existing

    bookings = Booking.objects.filter(
        corporate_account=account,
        status=Booking.Status.APPROVED,
        check_in__lte=period_end,
    )
    line_items = []
    total = 0
    for booking in bookings.select_related("room", "tenant"):
        line_items.append(
            {
                "booking_id": booking.pk,
                "tenant": booking.tenant.get_full_name() or booking.tenant.username,
                "room_title": booking.room.title,
                "monthly_rent": str(booking.monthly_rent),
            }
        )
        total += booking.monthly_rent

    invoice = CorporateInvoice.objects.create(
        account=account,
        invoice_number=next_invoice_number(),
        period_start=period_start,
        period_end=period_end,
        amount=total,
        line_items=line_items,
    )
    return invoice
