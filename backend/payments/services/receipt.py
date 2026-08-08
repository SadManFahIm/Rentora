"""Payment receipt PDF generation (reportlab — pure Python, no system deps)."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

if TYPE_CHECKING:
    from payments.models import Payment


def generate_receipt_pdf(payment: Payment) -> bytes:
    """Render a one-page PDF receipt for a successful payment."""
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
    tenant = payment.user

    # Listing-promotion payments have no booking — render the promoted room
    # and its owner instead of booking fields.
    if booking is None:
        room = payment.room
        landlord = room.owner
    else:
        room = booking.room
        landlord = room.owner

    elements = [
        Paragraph("Rentora", styles["Title"]),
        Paragraph("Payment Receipt", styles["Heading2"]),
        Spacer(1, 8 * mm),
    ]

    rows = [
        ["Transaction ID", payment.transaction_id],
        ["Gateway Reference", payment.gateway_transaction_id or "-"],
        ["Amount", f"BDT {payment.amount:,.2f}"],
        ["Payment Method", payment.get_payment_method_display()],
        ["Payment Type", payment.get_payment_type_display()],
        ["Status", payment.get_status_display()],
        ["Date", payment.updated_at.strftime("%d %B %Y, %I:%M %p")],
        ["", ""],
        ["Room", room.title],
        ["Tenant", tenant.get_full_name() or tenant.username],
        ["Landlord", landlord.get_full_name() or landlord.username],
    ]
    if booking is not None:
        rows.append(["Booking Check-in", booking.check_in.strftime("%d %B %Y")])

    table = Table(rows, colWidths=[55 * mm, 105 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e5e7eb")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 12 * mm))
    elements.append(
        Paragraph(
            "This is a system-generated receipt and does not require a signature.",
            styles["Italic"],
        )
    )

    doc.build(elements)
    return buffer.getvalue()
