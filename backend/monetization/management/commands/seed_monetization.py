"""Seed the Phase 15 Monetization 2.0 defaults.

Creates the landlord subscription plans, commission rules, insurance/credit
partners + products, and a sample add-on provider with services. Idempotent —
safe to run repeatedly.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed default plans, commission rules, partners and sample add-ons."

    def handle(self, *args, **options):
        from marketplace.models import AddonProvider, AddonService
        from monetization.models import CommissionRule
        from partner_services.models import InsuranceProduct, Partner
        from subscriptions.models import Plan

        plans = [
            {
                "code": "landlord_basic",
                "name": "Landlord Basic",
                "description": "Dynamic price predictions and market insights.",
                "price": 299,
                "billing_cycle": "monthly",
                "features": ["price_prediction_v2", "market_report"],
            },
            {
                "code": "landlord_pro",
                "name": "Landlord Pro",
                "description": "Everything in Basic plus bulk management and analytics export.",
                "price": 499,
                "billing_cycle": "monthly",
                "features": [
                    "price_prediction_v2",
                    "market_report",
                    "analytics_export",
                    "bulk_booking",
                ],
            },
            {
                "code": "landlord_enterprise",
                "name": "Landlord Enterprise",
                "description": "Multi-property pricing automation with priority support.",
                "price": 999,
                "billing_cycle": "monthly",
                "features": [
                    "price_prediction_v2",
                    "market_report",
                    "analytics_export",
                    "bulk_booking",
                    "pricing_automation",
                ],
            },
        ]
        for data in plans:
            plan, created = Plan.objects.get_or_create(code=data["code"], defaults=data)
            if not created:
                for key, value in data.items():
                    setattr(plan, key, value)
                plan.save()

        rules = [
            ("broker", 2.0),
            ("corporate", 1.0),
            ("marketplace", 10.0),
            ("insurance", 8.0),
            ("credit", 3.0),
        ]
        for scope, rate in rules:
            CommissionRule.objects.update_or_create(
                scope=scope, defaults={"rate": rate, "active": True}
            )

        partner_ins, _ = Partner.objects.get_or_create(
            code="bikroy-insurance",
            defaults={"name": "Bikroy Insurance", "kind": "insurance", "enabled": True},
        )
        _partner_credit, _ = Partner.objects.get_or_create(
            code="bKash-credit",
            defaults={"name": "bKash Credit", "kind": "credit", "enabled": True},
        )
        insurance_products = [
            {
                "code": "tenant_cover",
                "name": "Tenant Cover",
                "coverage": {"fire": True, "theft": True, "liability": True},
                "price_monthly": 199,
            },
            {
                "code": "contents_cover",
                "name": "Contents Cover",
                "coverage": {"contents": True},
                "price_monthly": 129,
            },
        ]
        for data in insurance_products:
            InsuranceProduct.objects.update_or_create(
                code=data["code"], defaults={**data, "partner": partner_ins, "is_active": True}
            )

        # Sample provider: reuse an existing user if present, else skip.
        from django.contrib.auth import get_user_model

        User = get_user_model()
        sample_user = User.objects.filter(role=User.Role.LANDLORD).first() or User.objects.first()
        if sample_user is not None and not AddonProvider.objects.filter(user=sample_user).exists():
            provider = AddonProvider.objects.create(
                user=sample_user,
                business_name="Rentora Home Services",
                description="Curated move-in services for new tenants.",
                status=AddonProvider.Status.ACTIVE,
                commission_rate=90,
            )
            AddonService.objects.get_or_create(
                provider=provider,
                category="cleaning",
                title="Move-in deep clean",
                defaults={
                    "description": "Full deep clean before you move in.",
                    "price": 1500,
                    "unit": "job",
                },
            )
            AddonService.objects.get_or_create(
                provider=provider,
                category="relocation",
                title="Relocation assistance",
                defaults={
                    "description": "Help moving your belongings to your new room.",
                    "price": 2500,
                    "unit": "trip",
                },
            )
            AddonService.objects.get_or_create(
                provider=provider,
                category="insurance",
                title="Tenant contents insurance",
                defaults={
                    "description": "Protect your belongings for the lease period.",
                    "price": 199,
                    "unit": "month",
                },
            )

        self.stdout.write(self.style.SUCCESS("Monetization 2.0 defaults seeded."))
