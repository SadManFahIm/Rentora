"""Tests for the Celery wiring (eager mode by default, tasks registered)."""

from django.test import TestCase, override_settings


class CeleryWiringTests(TestCase):
    def test_tasks_are_registered(self):
        # Import the task modules first, exactly like a real worker would
        # (autodiscovery alone is timing-sensitive inside the test runner).
        import agents.tasks  # noqa: F401
        import ai_intelligence.tasks  # noqa: F401
        import analytics.tasks  # noqa: F401
        import fraud.tasks  # noqa: F401
        import payments.tasks  # noqa: F401
        import pricing.tasks  # noqa: F401
        import rooms.tasks  # noqa: F401
        import savedsearches.tasks  # noqa: F401
        import subscriptions.tasks  # noqa: F401
        import users.tasks  # noqa: F401
        from config.celery import app

        for task_name in [
            "rooms.tasks.expire_listing_tiers",
            "pricing.tasks.update_market_stats",
            "fraud.tasks.scan_all_rooms",
            "fraud.tasks.scan_room",
            "fraud.tasks.detect_rings",
            "payments.tasks.send_payment_reminders",
            "users.tasks.alert_kyc_sla_breaches",
            "savedsearches.tasks.check_saved_searches",
            "savedsearches.tasks.send_saved_search_digests",
            "analytics.tasks.generate_market_report",
            "subscriptions.tasks.process_subscription_renewals",
            "subscriptions.tasks.send_subscription_reminders",
            # Phase 17 — task stubs
            "fraud.tasks.rebuild_fraud_graph",
            "fraud.tasks.update_graph_incremental",
            "fraud.tasks.scan_review_trust",
            "fraud.tasks.detect_review_anomalies",
            "fraud.tasks.check_model_drift",
            "fraud.tasks.purge_expired_liveness",
            "fraud.tasks.alert_graph_anomalies",
            "fraud.tasks.scan_photo_geo_mismatches",
            # Phase 18 — AI Intelligence Layer
            "ai_intelligence.update_provider_health",
            "ai_intelligence.purge_old_execution_logs",
            # Phase 18.3 — Evaluation Framework
            "ai_intelligence.execute_evaluation_run",
            "ai_intelligence.cancel_stale_evaluation_runs",
            # Phase 18.4 — Alerts + Dashboard
            "ai_intelligence.evaluate_alert_rules",
            "ai_intelligence.warm_dashboard_cache",
            # Phase 19 — Agent SDK
            "agents.execute_agent_run",
            "agents.expire_proposals",
        ]:
            with self.subTest(task=task_name):
                self.assertIn(task_name, app.tasks)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    def test_beat_schedule_lists_all_maint_tasks(self):
        from django.conf import settings

        scheduled = set(settings.CELERY_BEAT_SCHEDULE.keys())
        self.assertEqual(
            scheduled,
            {
                "expire-listing-tiers",
                "update-market-stats",
                "scan-rooms-fraud",
                "send-payment-reminders",
                "alert-kyc-sla-breaches",
                "check-saved-searches",
                "send-saved-search-digests",
                "generate-market-report",
                "detect-fraud-rings",
                "process-subscription-renewals",
                "send-subscription-reminders",
                "purge-expired-analytics",
                # Phase 17 — Graph & Deep Trust
                "rebuild-fraud-graph",
                "update-graph-incremental",
                "scan-review-trust",
                "detect-review-anomalies",
                "check-model-drift",
                "purge-expired-liveness",
                "alert-graph-anomalies",
                "scan-photo-geo-mismatches",
                # Phase 18 — AI Intelligence Layer
                "update-ai-provider-health",
                "purge-old-ai-execution-logs",
                # Phase 18.3 — Evaluation Framework
                "cancel-stale-evaluation-runs",
                # Phase 18.4 — Alerts + Dashboard
                "evaluate-ai-alert-rules",
                "warm-ai-dashboard-cache",
                # Phase 19 — Agent SDK
                "expire-agent-proposals",
            },
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    def test_expire_listings_task_runs_eagerly(self):
        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from rooms.models import Room

        User = get_user_model()
        owner = User.objects.create_user(
            username="owner", email="owner@example.com", password="test12345"
        )
        expired = Room.objects.create(
            owner=owner,
            title="Expired Premium",
            description="d",
            room_type="single",
            price=8000,
            area="Mirpur",
            address="x",
            lat=23.8,
            lng=90.4,
            size_sqft=200,
            tier=Room.Tier.PREMIUM,
            tier_expires_at=timezone.now() - timezone.timedelta(hours=1),
            is_featured=True,
        )
        alive = Room.objects.create(
            owner=owner,
            title="Still Premium",
            description="d",
            room_type="single",
            price=8000,
            area="Mirpur",
            address="x",
            lat=23.8,
            lng=90.4,
            size_sqft=200,
            tier=Room.Tier.PREMIUM,
            tier_expires_at=timezone.now() + timezone.timedelta(days=1),
            is_featured=True,
        )

        from rooms.tasks import expire_listing_tiers

        result = expire_listing_tiers.delay()
        self.assertEqual(result.get()["expired"], 1)

        expired.refresh_from_db()
        alive.refresh_from_db()
        self.assertEqual(expired.tier, Room.Tier.FREE)
        self.assertFalse(expired.is_featured)
        self.assertEqual(alive.tier, Room.Tier.PREMIUM)
