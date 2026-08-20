"""Central revenue ledger — idempotent, audited money-movement records."""

from __future__ import annotations

from audit.services import log_action

from ..models import RevenueLedgerEntry

# Entry types that count as recognized platform revenue for the dashboard.
REVENUE_ENTRY_TYPES = (
    RevenueLedgerEntry.EntryType.SUBSCRIPTION_PAYMENT,
    RevenueLedgerEntry.EntryType.SUBSCRIPTION_RENEWAL,
    RevenueLedgerEntry.EntryType.LISTING_PROMOTION,
    RevenueLedgerEntry.EntryType.ADDON_SALE,
    RevenueLedgerEntry.EntryType.INSURANCE_POLICY,
    RevenueLedgerEntry.EntryType.CORPORATE_INVOICE,
)


def record_entry(
    *,
    entry_type: str,
    scope: str,
    user=None,
    gross: object,
    platform_amount: object | None = None,
    partner_amount: object = 0,
    source,
    idempotency_key: str | None = None,
    detail: dict | None = None,
) -> RevenueLedgerEntry:
    """Record one ledger entry, never twice.

    When ``idempotency_key`` collides with an existing entry the existing
    entry is returned unchanged (callers are free to re-fire on retries).
    Every new entry is appended to the audit log.
    """
    if idempotency_key:
        existing = RevenueLedgerEntry.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing

    entry = RevenueLedgerEntry.objects.create(
        entry_type=entry_type,
        scope=scope,
        user=user,
        gross_amount=gross,
        platform_amount=gross if platform_amount is None else platform_amount,
        partner_amount=partner_amount,
        source_type=source._meta.label,
        source_id=str(source.pk),
        idempotency_key=idempotency_key,
        detail=detail or {},
    )
    log_action(
        actor=user,
        action="revenue.ledger",
        target=entry,
        detail={
            "entry_type": entry_type,
            "scope": scope,
            "gross": str(entry.gross_amount),
            "platform": str(entry.platform_amount),
            "partner": str(entry.partner_amount),
        },
    )
    return entry
