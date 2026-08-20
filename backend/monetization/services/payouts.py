"""Payout lifecycle: request, approve, reject, mark paid.

All mutations are audit-trailed and the recipient is notified at each step.
Account details are masked before persistence.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from audit.services import log_action
from notifications.models import Notification
from notifications.utils import create_notification

from ..models import Commission, Payout

_DECIMAL_2 = Decimal("0.01")
HELD_STATUSES = (Payout.Status.PENDING, Payout.Status.APPROVED, Payout.Status.PAID)


class PayoutError(Exception):
    """Domain-level payout rejection (bad amount, insufficient balance)."""


def _mask_account(account: dict) -> dict:
    """Mask sensitive fields (account numbers, phone) for storage."""
    masked: dict = {}
    for key, value in (account or {}).items():
        text = str(value)
        if re.search(r"\d{4,}", text):
            text = re.sub(r"\d(?=\d{4})", "*", text)
        masked[key] = text
    return masked


def available_balance(user) -> Decimal:
    """Earned-but-unpaid commissions minus payouts already requested."""
    earned = (
        Commission.objects.filter(recipient=user, status=Commission.Status.PENDING).aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )
    held = (
        Payout.objects.filter(recipient=user, status__in=HELD_STATUSES).aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )
    return (Decimal(str(earned)) - Decimal(str(held))).quantize(_DECIMAL_2)


def request_payout(
    *,
    user,
    amount: object,
    method: str,
    account_details: dict | None = None,
) -> Payout:
    """Create a PENDING payout request for the user, or raise ``PayoutError``."""
    try:
        amount_dec = Decimal(str(amount)).quantize(_DECIMAL_2)
    except Exception as exc:
        raise PayoutError("Amount must be a valid number.") from exc

    if amount_dec <= 0:
        raise PayoutError("Amount must be greater than zero.")
    balance = available_balance(user)
    if amount_dec > balance:
        raise PayoutError(
            f"Requested {amount_dec} BDT exceeds your available balance of {balance} BDT."
        )

    payout = Payout.objects.create(
        recipient=user,
        amount=amount_dec,
        method=method,
        account_details=_mask_account(account_details or {}),
        period_start=date.today().replace(day=1),
        period_end=date.today(),
    )
    create_notification(
        user=user,
        notification_type=Notification.Type.PAYOUT_REQUESTED,
        title="Payout requested",
        message=f"Your payout request of {amount_dec} BDT is being reviewed.",
        action_url="/dashboard?tab=broker",
    )
    log_action(
        actor=user,
        action="payout.requested",
        target=payout,
        detail={"amount": str(amount_dec), "method": method},
    )
    return payout


def _decide(payout: Payout, *, status, actor, reason: str = "", notification_type, title, message):
    payout.status = status
    payout.reason = reason
    payout.decided_at = timezone.now()
    payout.decided_by = actor
    payout.save(update_fields=["status", "reason", "decided_at", "decided_by", "updated_at"])
    create_notification(
        user=payout.recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        action_url="/dashboard?tab=broker",
    )
    log_action(actor=actor, action=f"payout.{status}", target=payout, detail={"reason": reason})
    return payout


def approve_payout(payout: Payout, actor) -> Payout:
    if payout.status != Payout.Status.PENDING:
        raise PayoutError(f"Cannot approve a {payout.status} payout.")
    return _decide(
        payout,
        status=Payout.Status.APPROVED,
        actor=actor,
        notification_type=Notification.Type.PAYOUT_APPROVED,
        title="Payout approved",
        message=f"Your payout of {payout.amount} BDT has been approved.",
    )


def reject_payout(payout: Payout, actor, reason: str = "") -> Payout:
    if payout.status != Payout.Status.PENDING:
        raise PayoutError(f"Cannot reject a {payout.status} payout.")
    return _decide(
        payout,
        status=Payout.Status.REJECTED,
        actor=actor,
        reason=reason,
        notification_type=Notification.Type.PAYOUT_REJECTED,
        title="Payout rejected",
        message=f"Your payout of {payout.amount} BDT was rejected."
        + (f" Reason: {reason}" if reason else ""),
    )


def mark_paid(payout: Payout, actor, reference: str = "") -> Payout:
    if payout.status != Payout.Status.APPROVED:
        raise PayoutError("Only approved payouts can be marked paid.")
    payout.status = Payout.Status.PAID
    payout.reference = reference
    payout.decided_at = timezone.now()
    payout.decided_by = actor
    payout.save(update_fields=["status", "reference", "decided_at", "decided_by", "updated_at"])
    create_notification(
        user=payout.recipient,
        notification_type=Notification.Type.PAYOUT_PAID,
        title="Payout sent",
        message=f"Your payout of {payout.amount} BDT has been sent.",
        action_url="/dashboard?tab=broker",
    )
    log_action(actor=actor, action="payout.paid", target=payout, detail={"reference": reference})
    return payout
