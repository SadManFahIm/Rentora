from django.apps import AppConfig


class AgentsConfig(AppConfig):
    """Agent SDK foundation — Phase 19.0.

    Provides the reusable, guarded layer future agents (Rental Agent,
    Listing Autopilot, Negotiation, Voice) are built on: agent registry,
    conversations/messages, runs, tool registry + execution, audited tool
    calls, human-review proposals, guardrails, and Phase 18 integration.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "agents"
    verbose_name = "Agents"
    default = True
