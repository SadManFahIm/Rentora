"""Agent SDK Celery tasks — Phase 19.0.

``agents.execute_agent_run`` runs the bounded session loop for one run.
Deliberately NO ``autoretry_for``/retry kwargs: retrying an agent run could
re-apply side effects or duplicate proposals. The session itself never
raises, so the task is a thin, idempotent dispatch wrapper.
"""

from celery import shared_task

from .models import AgentRun


@shared_task(name="agents.execute_agent_run", bind=True)
def execute_agent_run(self, run_id: int, request_id: str = "") -> dict:
    run = (
        AgentRun.objects.select_related("conversation", "conversation__agent")
        .filter(pk=run_id)
        .first()
    )
    if run is None:
        return {"run_id": run_id, "status": "missing"}

    # Idempotency guard — a completed/failed run must not be re-executed.
    if run.status not in ("pending", "running"):
        return {"run_id": run_id, "status": f"already_{run.status}"}

    from .session import AgentSession

    session = AgentSession(run.conversation, actor=run.created_by, request_id=request_id)
    session.execute(run)
    run.refresh_from_db()
    return {"run_id": run_id, "status": run.status, "termination_reason": run.termination_reason}


@shared_task(name="agents.expire_proposals")
def expire_proposals() -> dict:
    from .services import expire_proposals as expire_service

    return {"expired": expire_service()}


def schedule_agent_run(run: AgentRun) -> dict:
    """Dispatch a pending run to Celery. Returns task metadata."""
    task = execute_agent_run.delay(run.pk, request_id=str(run.run_key))
    return {"task_id": task.id if hasattr(task, "id") else "", "run_key": str(run.run_key)}
