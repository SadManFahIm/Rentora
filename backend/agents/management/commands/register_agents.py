from django.core.management.base import BaseCommand

from agents.services import register_agent


class Command(BaseCommand):
    help = "Seed the Phase 19.0 agent feature + one placeholder (disabled) agent."

    def handle(self, *args, **options):
        from ai_intelligence.services import register_feature

        register_feature(
            feature_id="rentora.agent",
            name="AI Agents",
            category="agent",
            description="Phase 19.0 Agent SDK — guarded agentic execution.",
            owner="platform",
            status="active",
            is_enabled=True,
            default_provider="llm",
            default_model="gpt-4o-mini",
            available_providers=["llm", "mock_llm"],
            fallback_strategy="none",
            feature_flag_key="",
            settings_key="AI_AGENT_LLM_PROVIDER",
        )

        try:
            from ai_intelligence.models import AIFeatureRegistry
            from ai_intelligence.services import create_prompt

            feature = AIFeatureRegistry.objects.get(feature_id="rentora.agent")
            create_prompt(
                prompt_key="rentora.agent.operator",
                name="Rentora Operator system prompt",
                template=(
                    "You are {agent_name}, a helpful assistant on the Rentora "
                    "platform. You answer only from tool results and never "
                    "show state-changing actions stay pending until a human "
                    "approves."
                ),
                description="Default system prompt template for operator agents.",
                feature_id=feature.pk,
                template_type="system",
                variables={},
            )
            self.stdout.write("created prompt rentora.agent.operator (draft)")
        except Exception as exc:
            self.stdout.write(f"prompt exists or skipped: {type(exc).__name__}")

        agent = register_agent(
            key="rentora.operator",
            name="Rentora Operator",
            description=(
                "Placeholder agent for the Phase 19.0 SDK. Disabled until a "
                "system prompt is activated and a provider is configured."
            ),
            status="disabled",
            audience="staff",
            permission="operator",
            feature_id="rentora.agent",
            prompt_key="rentora.agent.operator",
            provider="llm",
            model_name="gpt-4o-mini",
        )
        self.stdout.write(
            self.style.SUCCESS(f"registered agent {agent.key} (status={agent.status})")
        )
