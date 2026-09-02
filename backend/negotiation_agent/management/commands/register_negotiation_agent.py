"""Seed the Phase 19.4 AI Negotiation Agent (idempotent).

Creates/updates:
* AI feature ``rentora.negotiation_agent`` linked to feature flag
  ``ai.negotiation_agent`` (created DISABLED by default — the agent is not
  live until an operator flips it).
* Feature flag ``ai.negotiation_agent`` (disabled by default).
* Prompt ``rentora.negotiation_agent`` (v1 rendered as the agent's system
  prompt, source of truth = the Prompt Registry, never duplicated in logic)
  and activates its newest version.
* Agent ``ai.negotiation_agent`` (disabled by default): audience=users,
  permission=admin (needed for the HIGH_RISK accept/finalize ceiling; the
  executors still gate every action to participant + explicit consent),
  provider=llm, enabled tools = the negotiation tools + the reused read tools
  (``room.by_id``, ``price.compare``, ``property.intelligence``).

Safe to re-run: everything is an upsert or a no-op.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from negotiation_agent import constants as C

ENABLED_TOOLS = [
    C.CONTEXT_TOOL,
    C.HISTORY_TOOL,
    C.SET_BOUNDARY_TOOL,
    C.CREATE_OFFER_TOOL,
    C.COUNTER_OFFER_TOOL,
    C.SEND_TOOL,
    C.ACCEPT_TOOL,
    C.FINALIZE_TOOL,
    # Reused READ_ONLY grounding tools (never duplicated).
    "room.by_id",
    "price.compare",
    "property.intelligence",
]

SYSTEM_PROMPT = """You are {agent_name}, Rentora's AI negotiation assistant for renters and landlords in Bangladesh.

You answer in the language the user speaks: Bangla, English, Banglish, or any natural mix. Be concise, neutral and concrete.

ABSOLUTE GROUNDING RULES
- NEVER invent rent amounts, market prices, offers, acceptance, urgency, the other party's willingness, income or intent. Every fact about the listing, its market comparison, Property Intelligence and the negotiation itself must come from a tool result in THIS conversation.
- Prefer {context} before drafting anything: it returns the listing, price insight, your OWN boundaries and the real chat with the other party. Never state the counterparty's private boundaries — they are not in the data.
- When data is missing (no market comparison, no PI badge, no prior offers), say so plainly. Never extrapolate.
- Do not impersonate the other party or speak on their behalf.

NEGOTIATION RULES
- Help the user prepare: summarize the listing, the market comparison and their own boundaries; propose 1-3 grounded options (amount + short message), active voice, polite.
- Drafting is always a two-step consent: {create_offer}/{counter_offer} creates a DRAFT for the user to review; {send} sends it (its own approval). Never call {send} until the user has explicitly confirmed the exact amount and text.
- {set_boundary} records the user's OWN limits — only ever the values the user gives, never guesses.
- Acceptance ({accept}) and closing ({finalize}) are HIGH-RISK: the user must explicitly approve them in this chat. You never accept, close, book, charge or commit on your own; finalization only hands both sides to the existing booking flow.
- If a negotiation or offer is stale/expired/terminal, state the current status from {history}/{context} and do not attempt further actions.

FAILURE POLICY
- If a tool errors or a state change is refused, repeat the server's reason verbatim; never pretend a failed action succeeded.
- Never bypass consent: no action you propose executes without the user approving the on-screen consent request.
"""


class Command(BaseCommand):
    help = "Seed the Phase 19.4 AI Negotiation Agent (feature + flag + prompt + agent)."

    def handle(self, *args, **options):
        from agents.services import register_agent
        from ai_intelligence.models import AIFeatureRegistry
        from ai_intelligence.services import (
            activate_prompt_version,
            create_prompt,
            register_feature,
        )
        from feature_flags.models import FeatureFlag, invalidate_cache

        # 1. Feature + flag (agent gated by ai.negotiation_agent, disabled default).
        Flag, _ = FeatureFlag.objects.update_or_create(
            key=C.FLAG_KEY,
            defaults={
                "label": "AI Negotiation Agent (Phase 19.4)",
                "description": (
                    "Participant-scoped negotiation assistant for tenants and "
                    "landlords: grounded market context, boundary tracking, "
                    "draft→review→consent offer flow, counter offers, accepted "
                    "state machine and a booking hand-off. Never autonomous."
                ),
                "owner": "ai@rentora.com",
                "status": "disabled",
                "rollout_percentage": 0,
                "cleanup_plan": "Enable after consent UX + throttle validated; make core.",
            },
        )
        invalidate_cache(C.FLAG_KEY)
        self.stdout.write(f"flag {C.FLAG_KEY} -> {Flag.status} (flip to 'enabled' to go live)")

        register_feature(
            feature_id=C.FEATURE_ID,
            name="AI Negotiation Agent",
            category="agent",
            description=(
                "Phase 19.4 two-party negotiation agent built on the 19.0 SDK — "
                "grounded market reasoning + explicit two-step consent for every "
                "offer/send/accept/finalize."
            ),
            owner="ai@rentora.com",
            status="active",
            is_enabled=True,
            default_provider="llm",
            default_model="gpt-4o-mini",
            available_providers=["llm", "mock_llm"],
            fallback_strategy="none",
            feature_flag_key=C.FLAG_KEY,
            settings_key="AI_NEGOTIATION_AGENT_LLM_PROVIDER",
        )
        feature = AIFeatureRegistry.objects.get(feature_id=C.FEATURE_ID)

        # 2. Prompt in the registry (idempotent: skip duplicates, keep). Always
        #    re-activate the newest version so the agent runs on the newest
        #    grounded prompt.
        from ai_intelligence.models import AIPrompt, AIPromptVersion

        prompt_exists = AIPrompt.objects.filter(prompt_key=C.PROMPT_KEY).exists()
        if not prompt_exists:
            create_prompt(
                prompt_key=C.PROMPT_KEY,
                name="Rentora AI Negotiation Agent — system prompt",
                template=SYSTEM_PROMPT,
                description=(
                    "Grounding + consent + state-machine rules for the Phase 19.4 "
                    "negotiation agent."
                ),
                feature_id=feature.pk,
                template_type="system",
                variables={},
                change_summary="Phase 19.4 initial system prompt (agentic, "
                "grounded-only, two-step consent, no autonomous close).",
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

        # 3. Agent definition (disabled by default; permission=admin so the
        #    HIGH_RISK accept/finalize become participant-consentable — the
        #    executors still gate each action to the acting participant's own
        #    negotiation, and every apply is human-reviewed first).
        agent = register_agent(
            key=C.AGENT_KEY,
            name=C.AGENT_NAME,
            description=(
                "Two-party rent negotiation assistant: grounded market context, "
                "your explicit boundaries, draft→review→consent offers and counter "
                "offers, and a booking hand-off — never autonomous."
            ),
            status="disabled",
            audience="users",
            permission="admin",
            feature_id=C.FEATURE_ID,
            prompt_key=C.PROMPT_KEY,
            provider="llm",
            model_name="gpt-4o-mini",
            enabled_tools=ENABLED_TOOLS,
            max_turns=6,
            max_tool_calls=24,
            max_tokens=4000,
            timeout_seconds=60,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"agent {agent.key} ready (status={agent.status}, "
                f"feature={C.FEATURE_ID}, flag={C.FLAG_KEY})"
            )
        )
