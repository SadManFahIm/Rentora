"""AI Negotiation Agent constants + settings (Phase 19.4).

Every threshold/limit is configurable through Django settings so the staged
rollout never requires a code change to tune. Defaults are conservative and
documented. The negotiation domain (state machine, stale protection, expiry,
grounding) is enforced server-side in ``models`` / ``services`` — nothing the
LLM says can override it.
"""

from django.conf import settings

AGENT_KEY = "ai.negotiation_agent"
AGENT_NAME = "Rentora AI Negotiation Agent"
FEATURE_ID = "rentora.negotiation_agent"
FLAG_KEY = "ai.negotiation_agent"
PROMPT_KEY = "rentora.negotiation_agent"

# Tool names (registered in ``tools.register_negotiation_agent_tools``).
CONTEXT_TOOL = "negotiation.context"
HISTORY_TOOL = "negotiation.history"
SET_BOUNDARY_TOOL = "negotiation.set_boundary"
CREATE_OFFER_TOOL = "negotiation.create_offer"
COUNTER_OFFER_TOOL = "negotiation.counter_offer"
SEND_TOOL = "message.send"
ACCEPT_TOOL = "negotiation.accept"
FINALIZE_TOOL = "negotiation.finalize"

# Every tool this phase introduces. ``consent`` (self-)approval is only ever
# meaningful for these; the SDK proposals for any other tool are out of scope
# for participant self-consent (staff/admin review still applies).
NEGOTIATION_TOOLS = (
    CONTEXT_TOOL,
    HISTORY_TOOL,
    SET_BOUNDARY_TOOL,
    CREATE_OFFER_TOOL,
    COUNTER_OFFER_TOOL,
    SEND_TOOL,
    ACCEPT_TOOL,
    FINALIZE_TOOL,
)


def int_setting(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def bool_setting(name: str, default: bool) -> bool:
    return bool(getattr(settings, name, default))


class NegotiationSettings:
    """Namespaced access to the 19.4 settings block (read live from Django's
    settings so schedule/override changes apply without reloading)."""

    @property
    def enabled(self) -> bool:
        return bool_setting("NEGOTIATION_AGENT_ENABLED", True)

    @property
    def offer_ttl_days(self) -> int:
        return int_setting("NEGOTIATION_AGENT_OFFER_TTL_DAYS", 7)

    @property
    def negotiation_ttl_days(self) -> int:
        return int_setting("NEGOTIATION_AGENT_NEGOTIATION_TTL_DAYS", 30)

    @property
    def context_messages(self) -> int:
        return int_setting("NEGOTIATION_AGENT_CONTEXT_MESSAGES", 20)

    @property
    def max_open_offers(self) -> int:
        """Cap of non-terminal offers per negotiation (spam guard)."""
        return int_setting("NEGOTIATION_AGENT_MAX_OPEN_OFFERS", 5)

    @property
    def min_amount(self) -> int:
        return int_setting("NEGOTIATION_AGENT_MIN_AMOUNT", 1)

    @property
    def max_amount(self) -> int:
        return int_setting("NEGOTIATION_AGENT_MAX_AMOUNT", 5_000_000)

    @property
    def max_message_len(self) -> int:
        return int_setting("NEGOTIATION_AGENT_MAX_MESSAGE_LEN", 2000)
