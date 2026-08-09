"""Send a reminder notification for rent that's due in 3 days.

Scheduling
----------
Also exposed as a Celery beat task (``payments.tasks.send_payment_reminders``,
once daily in ``CELERY_BEAT_SCHEDULE``). Both paths call the shared
:func:`payments.services.reminders.send_payment_reminders`, so they can never
drift. Run manually any time with::

    python manage.py send_payment_reminders
"""

from django.core.management.base import BaseCommand

from payments.services.reminders import send_payment_reminders


class Command(BaseCommand):
    help = "Notify tenants whose next monthly rent payment is due in 3 days."

    def handle(self, *args, **options):
        result = send_payment_reminders()
        self.stdout.write(
            self.style.SUCCESS(
                f"Sent {result['sent']} payment reminder(s) for {result['due_date']}."
            )
        )
