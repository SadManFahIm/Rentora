"""Listing Autopilot constants + settings (Phase 19.3).

Every threshold/limit is configurable through Django settings so the staged
rollout never requires a code change to tune. Defaults are safe and
documented; the deterministic backend owns all score/price/eligibility/validity
decisions (no LLM, no invented rules).
"""

from django.conf import settings

AGENT_KEY = "ai.listing_autopilot"
AGENT_NAME = "Rentora AI Listing Autopilot"
FEATURE_ID = "rentora.listing_autopilot"
FLAG_KEY = "ai.listing_autopilot"
PROMPT_KEY = "rentora.listing_autopilot"

# Proposal types the autopilot can emit (mirrors ProposalType in models).
PROPOSAL_TYPES = (
    "TITLE_UPDATE",
    "DESCRIPTION_UPDATE",
    "AMENITY_UPDATE",
    "PHOTO_RECOMMENDATION",
    "PRICE_UPDATE",
    "LISTING_RENEWAL",
)

# Content-length thresholds reused for content-gap detection (aligned with the
# listing-quality engine's sentinels so both surfaces agree).
MIN_TITLE_LEN = 8
GOOD_DESCRIPTION_LEN = 200
MIN_DESCRIPTION_LEN = 80
GOOD_PHOTO_COUNT = 4
MIN_PHOTO_COUNT = 1


def int_setting(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def float_setting(name: str, default: float) -> float:
    try:
        return float(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def bool_setting(name: str, default: bool) -> bool:
    return bool(getattr(settings, name, default))


class AutopilotSettings:
    """Namespaced access to the 19.3 settings block (read live from Django's
    settings so schedule/override changes apply without reloading)."""

    @property
    def enabled(self) -> bool:
        return bool_setting("LISTING_AUTOPILOT_ENABLED", True)

    @property
    def stale_threshold_days(self) -> int:
        return int_setting("LISTING_AUTOPILOT_STALE_DAYS", 45)

    @property
    def min_analysis_score(self) -> int:
        return int_setting("LISTING_AUTOPILOT_MIN_SCORE", 0)

    @property
    def rollout_week_keys(self) -> list[str]:
        """Optional allow-list of ISO week keys ('' = all)."""
        raw = getattr(settings, "LISTING_AUTOPILOT_ROLLOUT_WEEK_KEYS", []) or []
        if isinstance(raw, str):
            return [k.strip() for k in raw.split(",") if k.strip()]
        return [str(k) for k in raw]

    def week_in_rollout(self, week_key: str) -> bool:
        keys = self.rollout_week_keys
        if not keys:
            return True
        return week_key in keys
