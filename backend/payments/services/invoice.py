"""Invoice PDF generation (reportlab, matching payments/services/receipt.py).

An invoice is distinct from a receipt: a receipt confirms a specific payment
already happened; an invoice is the formal bill — invoice number, billing
period, itemized breakdown, and payment terms/due date — for that same
payment. Both are one-page PDFs rendered on demand, never stored on disk.
"""

from __future__ import annotations

import io
from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

if TYPE_CHECKING:
    from payments.models import Invoice, Payment

INVOICE_NUMBER_PREFIX = "INV"
# Net terms: payment is due this many days after the invoice is issued.
PAYMENT_TERMS_DAYS = 15
_MAX_ALLOCATION_ATTEMPTS = 3


def _billing_period(payment: "Payment") -> tuple[date, date]:
    """The calendar month a rent/deposit payment is understood to cover.

    Payment doesn't carry an explicit billing-period field today, so the
    invoice's period is derived from the month the payment was created in.
    """
    anchor = payment.created_at.date()
    period_start = anchor.replace(day=1)
    if anchor.month == 12:
        next_month_start = anchor.replace(year=anchor.year + 1, month=1, day=1)
    else:
        next_month_start = anchor.replace(month=anchor.month + 1, day=1)
    period_end = next_month_start - timedelta(days=1)
    return period_start, period_end


def _allocate_invoice_number(year: int) -> str:
    """Allocate the next sequential number for ``year``, e.g. INV-2026-0001.

    Must run inside the same `transaction.atomic()` block that inserts the
    Invoice row — `select_for_update` here locks any existing rows for the
    year so concurrent callers are serialized onto strictly increasing
    numbers instead of racing for the same one.
    """
    from payments.models import Invoice

    prefix = f"{INVOICE_NUMBER_PREFIX}-{year}-"
    last = (
        Invoice.objects.select_for_update()
        .filter(invoice_number__startswith=prefix)
        .order_by("-invoice_number")
        .first()
    )
    next_seq = 1
    if last is not None:
        try:
            next_seq = int(last.invoice_number.rsplit("-", 1)[-1]) + 1
        except ValueError:
            next_seq = Invoice.objects.filter(invoice_number__startswith=prefix).count() + 1
    return f"{prefix}{next_seq:04d}"


def get_or_create_invoice_for_payment(payment: "Payment") -> "Invoice":
    """Fetch this payment's invoice, creating it on first request.

    Idempotent and safe to call on every GET. A payment gets at most one
    invoice (`Invoice.payment` is a `OneToOneField`); the sequential number
    is only ever allocated once, the first time an invoice is requested.
    """
    from payments.models import Invoice
    from payments.models import Payment as PaymentModel

    try:
        return _sync_invoice_status(payment.invoice, payment)
    except Invoice.DoesNotExist:
        pass

    period_start, period_end = _billing_period(payment)

    for attempt in range(_MAX_ALLOCATION_ATTEMPTS):
        try:
            with transaction.atomic():
                year = timezone.now().year
                invoice = Invoice.objects.create(
                    booking=payment.booking,
                    payment=payment,
                    invoice_number=_allocate_invoice_number(year),
                    period_start=period_start,
                    period_end=period_end,
                    amount=payment.amount,
                    status=Invoice.Status.DRAFT,
                )
            return _sync_invoice_status(invoice, payment)
        except IntegrityError:
            # Lost a race to another concurrent request — either this same
            # payment's invoice now exists, or another payment grabbed the
            # same invoice number and needs a fresh allocation. Either way,
            # re-check and retry rather than assuming which one happened.
            try:
                return _sync_invoice_status(payment.invoice, payment)
            except Invoice.DoesNotExist:
                continue

    raise RuntimeError("Could not allocate a unique invoice number after retrying.")


def _sync_invoice_status(invoice: "Invoice", payment: "Payment") -> "Invoice":
    from payments.models import Invoice
    from payments.models import Payment as PaymentModel

    target_status = Invoice.Status.PAID if payment.status == PaymentModel.Status.SUCCESS else Invoice.Status.SENT
    # Never downgrade a paid invoice — a later refund doesn't retroactively
    # make it "not yet paid".
    if invoice.status != target_status and invoice.status != Invoice.Status.PAID:
        invoice.status = target_status
        invoice.save(update_fields=["status", "updated_at"])
    return invoice


def generate_invoice_pdf(payment: "Payment") -> bytes:
    """Render a one-page PDF invoice for ``payment``, allocating its
    sequential invoice number on first call."""
    invoice = get_or_create_invoice_for_payment(payment)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    booking = payment.booking
    room = booking.room
    landlord = room.owner
    tenant = payment.user
    due_date = invoice.created_at.date() + timedelta(days=PAYMENT_TERMS_DAYS)

    elements = [
        Paragraph("Rentora", styles["Title"]),
        Paragraph("Invoice", styles["Heading2"]),
        Spacer(1, 6 * mm),
    ]

    header_rows = [
        ["Invoice Number", invoice.invoice_number],
        ["Invoice Date", invoice.created_at.strftime("%d %B %Y")],
        ["Payment Terms", f"Net {PAYMENT_TERMS_DAYS} days"],
        ["Due Date", due_date.strftime("%d %B %Y")],
        ["Billing Period", f"{invoice.period_start:%d %b %Y} - {invoice.period_end:%d %b %Y}"],
        ["Status", invoice.get_status_display()],
    ]
    header_table = Table(header_rows, colWidths=[45 * mm, 115 * mm])
    header_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e5e7eb")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
            ]
        )
    )
    elements.append(header_table)
    elements.append(Spacer(1, 8 * mm))

    elements.append(Paragraph("Billed To (Tenant)", styles["Heading4"]))
    elements.append(Paragraph(tenant.get_full_name() or tenant.username, styles["Normal"]))
    if tenant.email:
        elements.append(Paragraph(tenant.email, styles["Normal"]))
    if tenant.phone:
        elements.append(Paragraph(tenant.phone, styles["Normal"]))
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph("Billed By (Landlord)", styles["Heading4"]))
    elements.append(Paragraph(landlord.get_full_name() or landlord.username, styles["Normal"]))
    if landlord.email:
        elements.append(Paragraph(landlord.email, styles["Normal"]))
    if landlord.phone:
        elements.append(Paragraph(landlord.phone, styles["Normal"]))
    elements.append(Spacer(1, 8 * mm))

    elements.append(Paragraph(f"Room: {room.title}", styles["Normal"]))
    elements.append(Spacer(1, 6 * mm))

    item_description = {
        payment.Type.MONTHLY_RENT: "Monthly Rent",
        payment.Type.SECURITY_DEPOSIT: "Security Deposit",
        payment.Type.BOOKING_DEPOSIT: "Booking Deposit",
    }.get(payment.payment_type, payment.get_payment_type_display())

    items = [["Description", "Amount (BDT)"], [item_description, f"{payment.amount:,.2f}"]]
    items_table = Table(items, colWidths=[120 * mm, 40 * mm])
    items_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
                ("LINEBELOW", (0, -1), (-1, -1), 1, colors.HexColor("#111827")),
            ]
        )
    )
    elements.append(items_table)
    elements.append(Spacer(1, 4 * mm))

    total_table = Table([["Total Due", f"BDT {payment.amount:,.2f}"]], colWidths=[120 * mm, 40 * mm])
    total_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(total_table)
    elements.append(Spacer(1, 12 * mm))
    elements.append(
        Paragraph(
            "Payment is due within the terms stated above. This is a "
            "system-generated invoice and does not require a signature.",
            styles["Italic"],
        )
    )

    doc.build(elements)
    return buffer.getvalue()
