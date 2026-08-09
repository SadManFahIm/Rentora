"""Celery tasks for the payments app — scheduled rent reminders."""

from celery import shared_task

from payments.services.reminders import send_payment_reminders as _send_payment_reminders


@shared_task
def send_payment_reminders():
    """Notify tenants whose next monthly rent payment is due in 3 days.

    Delegates to :func:`payments.services.reminders.send_payment_reminders` —
    the same code path as the ``send_payment_reminders`` management command.
    """
    return _send_payment_reminders()
