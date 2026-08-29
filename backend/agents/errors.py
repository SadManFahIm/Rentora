"""Phase 19 — Agent SDK exceptions."""


class AgentSessionError(ValueError):
    """Controlled, user-facing session error (never PII-laden)."""


class ProposalError(ValueError):
    """Controlled proposal lifecycle error."""


class AgentRegistryError(ValueError):
    """Controlled agent registry error."""
