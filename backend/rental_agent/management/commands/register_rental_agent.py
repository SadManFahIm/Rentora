"""Seed the Phase 19.2 AI Rental Agent (idempotent).

Creates/updates:
* AI feature ``rentora.rental_agent`` linked to feature flag ``ai.rental_agent``
  (the flag is created DISABLED by default — the agent is not live until an
  operator flips it).
* Feature flag ``ai.rental_agent`` (disabled by default).
* Prompt ``rentora.rental_agent`` (v1 rendered as the agent's system prompt,
  source of truth = the Prompt Registry, never duplicated in logic) and
  activates its newest version.
* Agent ``ai.rental_agent`` (disabled by default): audience=users,
  permission=operator, provider=llm, enabled tools = the 5 Phase 19.2 domain
  tools + the Phase 19.1 ``property.intelligence`` tool.

Safe to re-run: everything is an upsert or a no-op.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from rental_agent.tools import (
    BOOKMARK_TOOL,
    COMMUTE_TOOL,
    PRICE_TOOL,
    ROOM_TOOL,
    SEARCH_TOOL,
)

FLAG_KEY = "ai.rental_agent"
FEATURE_ID = "rentora.rental_agent"
AGENT_KEY = "ai.rental_agent"
PROMPT_KEY = "rentora.rental_agent"

ENABLED_TOOLS = [
    SEARCH_TOOL,
    ROOM_TOOL,
    COMMUTE_TOOL,
    PRICE_TOOL,
    BOOKMARK_TOOL,
    "property.intelligence",
]

# Rendered as the agent's system prompt through the Phase 18.2 Prompt Registry.
# Grounded-only rules live here (registry), not in code.
SYSTEM_PROMPT = """You are {agent_name}, Rentora's AI rental assistant for tenants in Bangladesh.

You answer in the language the user speaks: Bangla, English, Banglish, or any
natural mix. Be concise, warm and concrete.

ABSOLUTE GROUNDING RULES
- NEVER invent a room, price, area, address, amenity, photo, landlord,
  distance, commute time, rating or booking state. Everything you state about
  a listing, price comparison, commute or Property Intelligence must come from
  an actual tool result in this conversation.
- When a tool has no data (no search hits, no market comparison yet, no
  transit route, unknown area), say plainly that the information is not yet
  available. Never extrapolate, guess or "fill in".
- "about X minutes" is an ESTIMATE from a heuristic — always say it is an
  estimate when the tool marks it as one.

DISCOVERY
- Find rooms with the {search} tool. Use the free-text query for Bangla/
  English/Banglish requests and add structured filters (budget_max, area,
  room_type, gender_preference) when the user states them or the intent is
  clear. Surface real, available listings only. When no matches, say so and
  offer to widen the budget or area.
- Answer concrete questions on one room with the {room} tool (details,
  condition, verification), the {price} tool (market comparison) and the
  {commute} tool (travel estimates, which are estimates).
- Offer the {intel} Property Intelligence badge when the user asks whether a
  listing is trustworthy or "good value".

ACTIONS NEED CONSENT
- Saving a room to bookmarks is a STATE-CHANGING action ({bookmark}). Before
  you call it, ask the user for explicit confirmation and explain exactly
  what will be saved and how to undo it (bookmarks section under the user's
  saved listings). The call does NOT save anything by itself: it creates a
  pending consent request the user must approve in the chat. If a consent
  request is already pending, never create a duplicate for the same room.

FAILURE POLICY
- If a tool errors, use the error's message as the answer; never pretend a
  failed call succeeded.
"""


class Command(BaseCommand):
    help = "Seed the Phase 19.2 AI Rental Agent (feature + flag + prompt + agent)."

    def handle(self, *args, **options):
        from agents.services import register_agent
        from ai_intelligence.models import AIFeatureRegistry
        from ai_intelligence.services import (
            activate_prompt_version,
            create_prompt,
            register_feature,
        )
        from feature_flags.models import FeatureFlag, invalidate_cache

        # 1. Feature + flag (agent gated by ai.rental_agent, disabled default).
        Flag, _ = FeatureFlag.objects.update_or_create(
            key=FLAG_KEY,
            defaults={
                "label": "AI Rental Agent (Phase 19.2)",
                "description": (
                    "Multi-turn Bangla/English/Banglish rental-agent chat that "
                    "discovers listings, answers grounded questions, compares "
                    "prices, estimates commutes and — only after explicit user "
                    "consent — saves rooms to bookmarks."
                ),
                "owner": "ai@rentora.com",
                "status": "disabled",
                "rollout_percentage": 0,
                "cleanup_plan": "Enable after chat UX + throttle validated; make core.",
            },
        )
        invalidate_cache(FLAG_KEY)
        self.stdout.write(f"flag {FLAG_KEY} -> {Flag.status} (flip to 'enabled' to go live)")

        register_feature(
            feature_id=FEATURE_ID,
            name="AI Rental Agent",
            category="agent",
            description=(
                "Phase 19.2 tenant-facing rental agent built on the 19.0 SDK — "
                "grounded tool reasoning + bookmark consent flow."
            ),
            owner="ai@rentora.com",
            status="active",
            is_enabled=True,
            default_provider="llm",
            default_model="gpt-4o-mini",
            available_providers=["llm", "mock_llm"],
            fallback_strategy="none",
            feature_flag_key=FLAG_KEY,
            settings_key="AI_RENTAL_AGENT_LLM_PROVIDER",
        )
        feature = AIFeatureRegistry.objects.get(feature_id=FEATURE_ID)

        # 2. Prompt in the registry (idempotent: skip duplicates, keep). Always
        #    re-activate the newest version so the agent runs on the newest
        #    grounded prompt.
        from ai_intelligence.models import AIPrompt, AIPromptVersion

        prompt_exists = AIPrompt.objects.filter(prompt_key=PROMPT_KEY).exists()
        if not prompt_exists:
            create_prompt(
                prompt_key=PROMPT_KEY,
                name="Rentora AI Rental Agent — system prompt",
                template=SYSTEM_PROMPT,
                description=(
                    "Grounding + consent + language rules for the Phase 19.2 tenant rental agent."
                ),
                feature_id=feature.pk,
                template_type="system",
                variables={},
                change_summary="Phase 19.2 initial system prompt (agentic, "
                "grounded-only, consent-gated bookmark).",
            )
            self.stdout.write(f"created prompt {PROMPT_KEY} (v1)")
        latest = (
            AIPromptVersion.objects.filter(prompt__prompt_key=PROMPT_KEY)
            .order_by("-version")
            .values_list("version", flat=True)
            .first()
        )
        if latest:
            activate_prompt_version(PROMPT_KEY, latest)
            self.stdout.write(f"activated prompt {PROMPT_KEY} v{latest}")

        # 3. Agent definition (disabled by default).
        agent = register_agent(
            key=AGENT_KEY,
            name="Rentora AI Rental Agent",
            description=(
                "Multi-turn tenant assistant: find rooms, compare prices, "
                "estimate commutes, explain Property Intelligence, and save "
                "rooms to your bookmarks with your consent."
            ),
            status="disabled",
            audience="users",
            permission="operator",
            feature_id=FEATURE_ID,
            prompt_key=PROMPT_KEY,
            provider="llm",
            model_name="gpt-4o-mini",
            enabled_tools=ENABLED_TOOLS,
            max_turns=6,
            max_tool_calls=20,
            max_tokens=4000,
            timeout_seconds=60,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"agent {agent.key} ready (status={agent.status}, "
                f"feature={FEATURE_ID}, flag={FLAG_KEY})"
            )
        )
