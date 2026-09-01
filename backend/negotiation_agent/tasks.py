"""AI Negotiation Agent Celery tasks — Phase 19.4.

``expire_negotiations`` is the only scheduled task: it expires stale SENT
offers and dormant open negotiations so a negotiation can never hang forever.
It is naturally idempotent (each pass only touches rows still in the expiring
state) and never raises.
"""

from celery import shared_task

from .services import expire_negotiations as _expire


@shared_task(name="negotiation_agent.expire_negotiations")
def expire_negotiations() -> dict:
    return _expire()
