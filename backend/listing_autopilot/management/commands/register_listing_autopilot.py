"""Seed the Phase 19.3 AI Listing Autopilot (idempotent).

Creates/updates:
* AI feature ``rentora.listing_autopilot`` linked to feature flag
  ``ai.listing_autopilot`` (the flag is created DISABLED by default — the
  autopilot is not live until an operator flips it).
* Feature flag ``ai.listing_autopilot`` (disabled by default).
* Prompt ``rentora.listing_autopilot`` (v1 rendered as the agent's system
  prompt; source of truth = the Prompt Registry, never duplicated in logic).
* Agent ``ai.listing_autopilot`` (disabled by default): audience=staff,
  permission=operator, provider=llm, enabled tools = the autopilot domain
  tools (analyze + the typed apply tools).

The autopilot runs on a schedule (``listing_autopilot.tasks.run_weekly_autopilot``)
and is feature-flag gated. The agent row exists so proposals, runs, tool calls
and telemetry hang off the same Phase 18/19 attribution model — but the agent is
*not* chat-invocable (staff audience, disabled status) and never self-approves.

Safe to re-run: everything is an upsert or a no-op.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from listing_autopilot import constants as C
from listing_autopilot.apply_tools import (
    _EXECUTORS,  # the typed apply tool slugs from the tool registry
)

SYSTEM_PROMPT = """You are {agent_name}, Rentora's AI Listing Autopilot for landlords.

You do NOT chat with landlords. You are a background analyser that runs on a
weekly schedule and produces typed, reviewable proposals for the landlord.

ABSOLUTE GROUNDING RULES
- NEVER invent a room, price, area, title, description, amenity, photo, score,
  or recommendation. Every value in a proposal comes from the deterministic
  analysis: listing quality, Property Intelligence, the price engine, and the
  listing's own stored fields.
- You may use LLM text generation ONLY to improve the wording of a title or
  description draft from grounded inputs — never to add facts that are not in
  the listing, and never for scores, prices, eligibility, permissions, validity
  or stale detection (those are always deterministic).
- A proposal is only ever PENDING. The landlord, and only the landlord,
  approves or rejects it. You never self-approve and never apply anything.

WHAT TRIGGERS A PROPOSAL
- Title that is sparse for the area/room type -> {title_update}.
- Description below the listing-quality threshold -> {description_update}.
- Missing common, verifiable amenities -> {amenity_update}.
- Fewer than the quality photo counts / no primary photo -> {photo_recommendation}.
- Price engine suggests a move (raise/lower with a grounded dynamic figure) ->
  {price_update}.
- Listing stale (no updates past the threshold) and low interest ->
  {listing_renewal}.

FAILURE POLICY
- If any reference engine errors, drop that proposal (never approximate with a
  fallback number); mark the analysis error and move on. Never partially apply
  a rejected/expired proposal.
"""


class Command(BaseCommand):
    help = "Seed the Phase 19.3 AI Listing Autopilot (feature + flag + prompt + agent + tools)."

    def handle(self, *args, **options):
        from agents.services import register_agent
        from ai_intelligence.models import AIFeatureRegistry
        from ai_intelligence.services import (
            activate_prompt_version,
            create_prompt,
            register_feature,
        )
        from feature_flags.models import FeatureFlag, invalidate_cache

        enabled_tools = ["listing.autopilot.analyze", *list(_EXECUTORS.keys())]
        # Map proposal types to their registered tool slugs for the registry.
        from listing_autopilot.apply_tools import register_listing_autopilot_tools

        register_listing_autopilot_tools()
        tool_slugs = [
            f"listing.autopilot.apply.{ptype.lower().replace('_', '-')}"
            for ptype in C.PROPOSAL_TYPES
        ]
        enabled_tools = ["listing.autopilot.analyze", *tool_slugs]

        # 1. Feature flag (disabled default).
        Flag, _ = FeatureFlag.objects.update_or_create(
            key=C.FLAG_KEY,
            defaults={
                "label": "AI Listing Autopilot (Phase 19.3)",
                "description": (
                    "Weekly, grounded listing recommendations for landlords: "
                    "title/description/amenities/photo/price/renewal, with "
                    "landlord approve-or-reject and replay-safe apply."
                ),
                "owner": "ai@rentora.com",
                "status": "disabled",
                "rollout_percentage": 0,
                "cleanup_plan": (
                    "Roll out by listing cohort (LISTING_AUTOPILOT_ROLLOUT_WEEK_KEYS "
                    "or flag rollout), then make core."
                ),
            },
        )
        invalidate_cache(C.FLAG_KEY)
        self.stdout.write(f"flag {C.FLAG_KEY} -> {Flag.status} (flip to 'enabled' to go live)")

        # 2. Feature registry row.
        register_feature(
            feature_id=C.FEATURE_ID,
            name="AI Listing Autopilot",
            category="agent",
            description=(
                "Phase 19.3 landlord-side autopilot on the 19.0 SDK: deterministic "
                "weekly analysis + typed approve/reject proposals + replay-safe apply."
            ),
            owner="ai@rentora.com",
            status="active",
            is_enabled=True,
            default_provider="llm",
            default_model="gpt-4o-mini",
            available_providers=["llm", "mock_llm"],
            fallback_strategy="none",
            feature_flag_key=C.FLAG_KEY,
            settings_key="AI_LISTING_AUTOPILOT_LLM_PROVIDER",
        )
        feature = AIFeatureRegistry.objects.get(feature_id=C.FEATURE_ID)

        # 3. Prompt (idempotent, re-activate newest).
        from ai_intelligence.models import AIPrompt, AIPromptVersion

        if not AIPrompt.objects.filter(prompt_key=C.PROMPT_KEY).exists():
            create_prompt(
                prompt_key=C.PROMPT_KEY,
                name="Rentora AI Listing Autopilot — system prompt",
                template=SYSTEM_PROMPT,
                description=(
                    "Grounding, trigger, LLM-usage and failure rules for the "
                    "Phase 19.3 weekly listing autopilot."
                ),
                feature_id=feature.pk,
                template_type="system",
                variables={},
                change_summary="Phase 19.3 initial system prompt (grounded-only, "
                "LLM limited to wording, landlord-only consent).",
            )
            self.stdout.write(f"created prompt {C.PROMPT_KEY} (v1)")
        latest = (
            AIPromptVersion.objects.filter(prompt__prompt_key=C.PROMPT_KEY)
            .order_by("-version")
            .values_list("version", flat=True)
            .first()
        )
        if latest:
            activate_prompt_version(C.PROMPT_KEY, latest)
            self.stdout.write(f"activated prompt {C.PROMPT_KEY} v{latest}")

        # 4. Agent definition (disabled; staff audience => not chat-invocable).
        agent = register_agent(
            key=C.AGENT_KEY,
            name=C.AGENT_NAME,
            description=(
                "Weekly, deterministic listing recommendations for landlords — "
                "title, description, amenities, photos, price and renewal, each "
                "grounded in stored listing data and reference engines; every "
                "action requires the landlord's approve/reject."
            ),
            status="disabled",
            audience="staff",
            permission="operator",
            feature_id=C.FEATURE_ID,
            prompt_key=C.PROMPT_KEY,
            provider="llm",
            model_name="gpt-4o-mini",
            enabled_tools=enabled_tools,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"agent {agent.key} ready (status={agent.status}, "
                f"feature={C.FEATURE_ID}, flag={C.FLAG_KEY})"
            )
        )
