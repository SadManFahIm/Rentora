"""AI Intelligence Layer — Phase 18.1 tests."""

import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone

from fraud.services import provider_base

from .models import AIExecutionLog, AIFeatureRegistry, ProviderHealth
from .services import (
    calculate_estimated_cost,
    get_provider_stats,
    log_execution,
    register_feature,
    update_provider_health,
)

User = get_user_model()


class AIFeatureRegistryModelTest(TestCase):
    """Tests for AIFeatureRegistry model."""

    def test_create_feature(self):
        feature = AIFeatureRegistry.objects.create(
            feature_id="test_feature",
            name="Test Feature",
            category="fraud",
            is_enabled=True,
            default_provider="rules",
            available_providers=["rules", "http"],
        )
        self.assertEqual(feature.feature_id, "test_feature")
        self.assertTrue(feature.is_enabled)
        self.assertEqual(feature.category, "fraud")

    def test_str_representation(self):
        feature = AIFeatureRegistry.objects.create(
            feature_id="test_feature",
            name="Test Feature",
            is_enabled=True,
        )
        self.assertEqual(str(feature), "test_feature (enabled)")

    def test_str_disabled(self):
        feature = AIFeatureRegistry.objects.create(
            feature_id="test_feature",
            name="Test Feature",
            is_enabled=False,
        )
        self.assertEqual(str(feature), "test_feature (disabled)")


class AIExecutionLogModelTest(TestCase):
    """Tests for AIExecutionLog model."""

    def test_create_execution_log(self):
        log = AIExecutionLog.objects.create(
            execution_id=uuid.uuid4(),
            feature_key="test_feature",
            provider="rules",
            status="success",
            latency_ms=100,
            confidence=0.85,
        )
        self.assertEqual(log.feature_key, "test_feature")
        self.assertEqual(log.status, "success")
        self.assertEqual(log.latency_ms, 100)

    def test_str_representation(self):
        log = AIExecutionLog.objects.create(
            execution_id=uuid.uuid4(),
            feature_key="test_feature",
            provider="rules",
            status="success",
            latency_ms=100,
        )
        self.assertIn("test_feature", str(log))
        self.assertIn("rules", str(log))
        self.assertIn("success", str(log))

    def test_execution_id_unique(self):
        exec_id = uuid.uuid4()
        AIExecutionLog.objects.create(
            execution_id=exec_id,
            feature_key="test_feature",
            provider="rules",
            status="success",
        )
        with self.assertRaises(IntegrityError):
            AIExecutionLog.objects.create(
                execution_id=exec_id,
                feature_key="test_feature",
                provider="rules",
                status="success",
            )


class ProviderHealthModelTest(TestCase):
    """Tests for ProviderHealth model."""

    def test_create_provider_health(self):
        health = ProviderHealth.objects.create(
            provider="rules",
            feature_key="test_feature",
            total_requests=100,
            successful_requests=95,
            failed_requests=5,
            avg_latency_ms=50,
            success_rate=0.95,
            window_start=timezone.now(),
            window_end=timezone.now(),
        )
        self.assertEqual(health.provider, "rules")
        self.assertEqual(health.success_rate, 0.95)
        self.assertTrue(health.is_healthy)

    def test_str_representation(self):
        health = ProviderHealth.objects.create(
            provider="rules",
            feature_key="test_feature",
            success_rate=0.95,
            is_healthy=True,
            window_start=timezone.now(),
            window_end=timezone.now(),
        )
        self.assertIn("rules", str(health))
        self.assertIn("test_feature", str(health))
        self.assertIn("95.0%", str(health))


class ServicesTest(TestCase):
    """Tests for AI Intelligence services."""

    def test_register_feature(self):
        feature = register_feature(
            feature_id="test_feature",
            name="Test Feature",
            category="fraud",
            default_provider="rules",
        )
        self.assertEqual(feature.feature_id, "test_feature")
        self.assertEqual(feature.name, "Test Feature")

    def test_register_feature_idempotent(self):
        register_feature(
            feature_id="test_feature",
            name="Test Feature",
        )
        register_feature(
            feature_id="test_feature",
            name="Updated Feature",
        )
        self.assertEqual(AIFeatureRegistry.objects.count(), 1)
        feature = AIFeatureRegistry.objects.get(feature_id="test_feature")
        self.assertEqual(feature.name, "Updated Feature")

    def test_log_execution(self):
        log = log_execution(
            execution_id=uuid.uuid4(),
            feature_id="test_feature_svc",
            provider="rules",
            status="success",
            latency_ms=100,
            confidence=0.85,
        )
        self.assertIsNotNone(log)
        self.assertEqual(log.feature_key, "test_feature_svc")

    def test_log_execution_failure(self):
        log = log_execution(
            execution_id=uuid.uuid4(),
            feature_id="test_feature_svc",
            provider="rules",
            status="failure",
            failure_type="provider_failure",
            error_message="Test error",
        )
        self.assertIsNotNone(log)
        self.assertEqual(log.status, "failure")

    def test_get_provider_stats(self):
        for i in range(10):
            log_execution(
                execution_id=uuid.uuid4(),
                feature_id="test_feature_stats",
                provider="rules",
                status="success" if i < 8 else "failure",
                latency_ms=50 + i * 10,
            )

        stats = get_provider_stats(feature_id="test_feature_stats", hours=1)
        self.assertEqual(stats["total_requests"], 10)
        self.assertEqual(stats["successful"], 8)
        self.assertEqual(stats["failed"], 2)
        self.assertAlmostEqual(stats["success_rate"], 0.8)

    def test_update_provider_health(self):
        feature_key = f"test_feature_health_{uuid.uuid4().hex[:8]}"
        provider_name = f"rules_health_{uuid.uuid4().hex[:8]}"

        actual_count = 0
        for _i in range(5):
            result = log_execution(
                execution_id=uuid.uuid4(),
                feature_id=feature_key,
                provider=provider_name,
                status="success",
                latency_ms=50,
            )
            if result is not None:
                actual_count += 1

        self.assertEqual(actual_count, 5, "All 5 logs should be created")

        updated = update_provider_health(hours=24)
        self.assertGreaterEqual(updated, 1)

        health = ProviderHealth.objects.get(
            provider=provider_name,
            feature_key=feature_key,
        )
        self.assertGreaterEqual(health.total_requests, 1)
        self.assertEqual(health.successful_requests, health.total_requests)
        self.assertTrue(health.is_healthy)


class CostCalculationTest(TestCase):
    """Tests for cost calculation."""

    def test_openai_gpt4o_cost(self):
        cost = calculate_estimated_cost(
            provider="openai",
            model_name="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
        )
        expected = Decimal("0.005") + Decimal("0.0075")
        self.assertEqual(cost, expected)

    def test_anthropic_cost(self):
        cost = calculate_estimated_cost(
            provider="anthropic",
            model_name="claude-3-haiku",
            input_tokens=2000,
            output_tokens=1000,
        )
        expected = Decimal("0.0005") + Decimal("0.00125")
        self.assertEqual(cost, expected)

    def test_unknown_provider_cost(self):
        cost = calculate_estimated_cost(
            provider="unknown",
            model_name="model",
            input_tokens=1000,
            output_tokens=500,
        )
        self.assertEqual(cost, Decimal("0"))

    def test_zero_tokens_cost(self):
        cost = calculate_estimated_cost(
            provider="openai",
            model_name="gpt-4o",
            input_tokens=0,
            output_tokens=0,
        )
        self.assertEqual(cost, Decimal("0"))


@override_settings(AI_TELEMETRY_ENABLED=True)
class TelemetryMixinTest(TestCase):
    """Tests for TelemetryMixin integration."""

    def setUp(self):
        provider_base._telemetry_enabled = None

    def tearDown(self):
        provider_base._telemetry_enabled = None

    def test_telemetry_mixin_logs_execution(self):
        from fraud.services.provider_base import BaseProvider, ProviderResult, TelemetryMixin

        class TestProvider(TelemetryMixin, BaseProvider):
            name = "test_telemetry"
            feature_id = "test_feature_tel"

            def _run(self, **kwargs):
                return ProviderResult.ok(
                    provider=self.name,
                    data={"test": True},
                    confidence=0.9,
                )

        provider = TestProvider()
        result = provider.run(user=None, request_id="test-request-123")

        self.assertTrue(result.success)
        self.assertGreaterEqual(result.latency_ms, 0)
        self.assertIn("execution_id", result.metadata)

        log = AIExecutionLog.objects.filter(
            feature_key="test_feature_tel",
            provider="test_telemetry",
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, "success")
        self.assertEqual(log.request_id, "test-request-123")

    def test_telemetry_mixin_failure_logging(self):
        from fraud.services.provider_base import (
            BaseProvider,
            FailureType,
            ProviderResult,
            TelemetryMixin,
        )

        class FailingProvider(TelemetryMixin, BaseProvider):
            name = "test_failing"
            feature_id = "test_feature_fail"

            def _run(self, **kwargs):
                return ProviderResult.fail(
                    provider=self.name,
                    reason="Test failure",
                    failure_type=FailureType.PROVIDER_FAILURE,
                )

        provider = FailingProvider()
        result = provider.run()

        self.assertFalse(result.success)

        log = AIExecutionLog.objects.filter(
            feature_key="test_feature_fail",
            provider="test_failing",
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, "failure")
        self.assertEqual(log.failure_type, "provider_failure")

    @override_settings(AI_TELEMETRY_ENABLED=False)
    def test_telemetry_disabled(self):
        provider_base._telemetry_enabled = None

        from fraud.services.provider_base import BaseProvider, ProviderResult, TelemetryMixin

        class TestProvider(TelemetryMixin, BaseProvider):
            name = "test_disabled"
            feature_id = "test_feature_disabled"

            def _run(self, **kwargs):
                return ProviderResult.ok(provider=self.name)

        provider = TestProvider()
        result = provider.run()

        self.assertTrue(result.success)
        self.assertEqual(result.latency_ms, 0)

        self.assertEqual(
            AIExecutionLog.objects.filter(
                feature_key="test_feature_disabled",
                provider="test_disabled",
            ).count(),
            0,
        )
