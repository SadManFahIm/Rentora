"""AI Intelligence Layer — Phase 18.1 + 18.2 + 18.3 tests."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from .models import AIExecutionLog, AIFeatureRegistry, AIPrompt, AIPromptVersion, ProviderHealth
from .services import (
    activate_prompt_version,
    create_prompt,
    create_prompt_version,
    deactivate_prompt_version,
    get_feature_registry,
    get_prompt_template,
    get_thresholds,
    is_feature_available,
    register_feature,
    register_metric,
    render_prompt,
    rollback_prompt,
    set_threshold,
    update_provider_health,
    validate_prompt_variables,
)
from .tasks import purge_old_execution_logs

User = get_user_model()


class AIFeatureRegistryModelTests(TestCase):
    def test_create_feature(self):
        f = AIFeatureRegistry.objects.create(
            feature_id="test.feature",
            name="Test Feature",
            category="other",
        )
        self.assertEqual(str(f), "test.feature (active)")

    def test_status_choices(self):
        f = AIFeatureRegistry.objects.create(
            feature_id="test.feature",
            name="Test Feature",
            status="beta",
        )
        self.assertEqual(f.status, "beta")


class AIFeatureRegistryServiceTests(TestCase):
    def test_register_creates_new(self):
        f = register_feature(
            feature_id="test.new",
            name="New Feature",
            category="fraud",
            owner="test@rentora.com",
            default_provider="rules",
            default_model="test-model",
        )
        self.assertEqual(f.feature_id, "test.new")
        self.assertEqual(f.owner, "test@rentora.com")
        self.assertEqual(f.default_model, "test-model")

    def test_register_updates_existing(self):
        register_feature(feature_id="test.dup", name="Original")
        updated = register_feature(feature_id="test.dup", name="Updated")
        self.assertEqual(updated.name, "Updated")

    def test_get_feature_registry(self):
        register_feature(feature_id="test.get", name="Get Feature")
        f = get_feature_registry("test.get")
        self.assertIsNotNone(f)
        self.assertEqual(f.feature_id, "test.get")

    def test_get_feature_registry_missing(self):
        f = get_feature_registry("nonexistent")
        self.assertIsNone(f)

    def test_is_feature_available_enabled(self):
        register_feature(feature_id="test.avail", name="Avail", is_enabled=True)
        self.assertTrue(is_feature_available("test.avail"))

    def test_is_feature_available_disabled(self):
        register_feature(feature_id="test.na", name="NA", is_enabled=False)
        self.assertFalse(is_feature_available("test.na"))

    def test_is_feature_available_missing(self):
        self.assertFalse(is_feature_available("nonexistent"))

    @override_settings(FEATURE_FLAGS={})
    def test_is_feature_available_with_flag_enabled(self):
        from feature_flags.models import FeatureFlag

        FeatureFlag.objects.create(
            key="test.flag.on",
            status="enabled",
            rollout_percentage=100,
        )
        register_feature(
            feature_id="test.flagged",
            name="Flagged",
            is_enabled=True,
            feature_flag_key="test.flag.on",
        )
        self.assertTrue(is_feature_available("test.flagged"))

    @override_settings(FEATURE_FLAGS={})
    def test_is_feature_available_with_flag_disabled(self):
        from feature_flags.models import FeatureFlag

        FeatureFlag.objects.create(
            key="test.flag.off",
            status="disabled",
            rollout_percentage=0,
        )
        register_feature(
            feature_id="test.flagged2",
            name="Flagged2",
            is_enabled=True,
            feature_flag_key="test.flag.off",
        )
        self.assertFalse(is_feature_available("test.flagged2"))


class AIPromptModelTests(TestCase):
    def setUp(self):
        self.feature = AIFeatureRegistry.objects.create(
            feature_id="test.prompt.feature",
            name="Test Prompt Feature",
        )

    def test_create_prompt(self):
        p = AIPrompt.objects.create(
            prompt_key="ai.test.prompt",
            name="Test Prompt",
            feature=self.feature,
        )
        self.assertEqual(str(p), "ai.test.prompt (draft)")
        self.assertIsNone(p.active_version)

    def test_prompt_active_version(self):
        p = AIPrompt.objects.create(prompt_key="ai.test.av", name="AV Test")
        v = AIPromptVersion.objects.create(
            prompt=p, version=1, template="Hello {{name}}", is_active=True, status="active"
        )
        self.assertEqual(p.active_version, v)

    def test_prompt_latest_version(self):
        p = AIPrompt.objects.create(prompt_key="ai.test.lv", name="LV Test")
        AIPromptVersion.objects.create(prompt=p, version=1, template="v1")
        v2 = AIPromptVersion.objects.create(prompt=p, version=2, template="v2")
        self.assertEqual(p.latest_version, v2)


class AIPromptVersionModelTests(TestCase):
    def setUp(self):
        self.prompt = AIPrompt.objects.create(prompt_key="ai.test.ver", name="Version Test")

    def test_create_version(self):
        v = AIPromptVersion.objects.create(prompt=self.prompt, version=1, template="Hello {{name}}")
        self.assertEqual(str(v), "ai.test.ver:v1 (inactive)")

    def test_unique_constraint(self):
        AIPromptVersion.objects.create(prompt=self.prompt, version=1, template="v1")
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            AIPromptVersion.objects.create(prompt=self.prompt, version=1, template="dup")

    def test_template_safety_rejects_api_key(self):
        v = AIPromptVersion(prompt=self.prompt, version=1, template="key=API_KEY123")
        with self.assertRaises(ValidationError):
            v.clean()

    def test_template_safety_rejects_secret(self):
        v = AIPromptVersion(prompt=self.prompt, version=1, template="password=secret123")
        with self.assertRaises(ValidationError):
            v.clean()

    def test_template_safety_allows_clean(self):
        v = AIPromptVersion(
            prompt=self.prompt, version=1, template="Hello {{name}}, your room is ready."
        )
        v.clean()  # should not raise


class PromptCRUDServiceTests(TestCase):
    def test_create_prompt_with_version(self):
        p = create_prompt(
            prompt_key="ai.test.create",
            name="Create Test",
            template="Find rooms in {{location}} under {{budget}}",
            description="Test prompt",
            category="search",
            template_type="template",
            variables={
                "location": {"type": "string", "required": True},
                "budget": {"type": "integer", "required": True, "default": 15000},
            },
            model_requirement="gpt-4o",
        )
        self.assertEqual(p.prompt_key, "ai.test.create")
        self.assertEqual(p.versions.count(), 1)
        v1 = p.versions.first()
        self.assertEqual(v1.version, 1)
        self.assertFalse(v1.is_active)

    def test_create_prompt_duplicate_key_raises(self):
        create_prompt(prompt_key="ai.test.dup", name="Dup", template="Hello")
        with self.assertRaises(Exception):  # noqa: B017
            create_prompt(prompt_key="ai.test.dup", name="Dup2", template="World")

    def test_create_prompt_version(self):
        create_prompt(prompt_key="ai.test.cv", name="CV", template="v1")
        v2 = create_prompt_version(
            prompt_key="ai.test.cv",
            template="v2 with {{var}}",
            change_summary="Added variable",
        )
        self.assertEqual(v2.version, 2)
        self.assertFalse(v2.is_active)

    def test_create_prompt_version_missing_prompt(self):
        with self.assertRaises(ValueError):
            create_prompt_version(prompt_key="nonexistent", template="x")


class PromptVersioningServiceTests(TestCase):
    def setUp(self):
        self.prompt = create_prompt(
            prompt_key="ai.test activate",
            name="Activate Test",
            template="v1 template",
        )

    def test_activate_version(self):
        pv = activate_prompt_version("ai.test activate", 1)
        self.assertTrue(pv.is_active)
        self.assertEqual(pv.status, "active")

    def test_activate_deactivates_previous(self):
        activate_prompt_version("ai.test activate", 1)
        # Create and activate v2
        create_prompt_version("ai.test activate", template="v2")
        pv2 = activate_prompt_version("ai.test activate", 2)
        self.assertTrue(pv2.is_active)
        # v1 should be deactivated
        v1 = AIPromptVersion.objects.get(prompt=self.prompt, version=1)
        self.assertFalse(v1.is_active)

    def test_activate_nonexistent_version(self):
        with self.assertRaises(ValueError):
            activate_prompt_version("ai.test activate", 999)

    def test_deactivate_version(self):
        activate_prompt_version("ai.test activate", 1)
        result = deactivate_prompt_version("ai.test activate")
        self.assertTrue(result)
        v1 = AIPromptVersion.objects.get(prompt=self.prompt, version=1)
        self.assertFalse(v1.is_active)

    def test_deactivate_no_active(self):
        result = deactivate_prompt_version("ai.test activate")
        self.assertFalse(result)


class PromptRollbackServiceTests(TestCase):
    def setUp(self):
        self.prompt = create_prompt(
            prompt_key="ai.test.rollback",
            name="Rollback Test",
            template="v1",
        )
        create_prompt_version("ai.test.rollback", template="v2")
        create_prompt_version("ai.test.rollback", template="v3")

    def test_rollback_to_previous(self):
        activate_prompt_version("ai.test.rollback", 3)
        pv = rollback_prompt("ai.test.rollback")
        self.assertEqual(pv.version, 2)
        self.assertTrue(pv.is_active)

    def test_rollback_from_v1_raises(self):
        activate_prompt_version("ai.test.rollback", 1)
        with self.assertRaises(ValueError):
            rollback_prompt("ai.test.rollback")

    def test_rollback_no_active_raises(self):
        with self.assertRaises(ValueError):
            rollback_prompt("ai.test.rollback")


class PromptRenderingServiceTests(TestCase):
    def setUp(self):
        self.prompt = create_prompt(
            prompt_key="ai.test.render",
            name="Render Test",
            template="Find {{location}} rooms under {{budget}} BDT",
            variables={
                "location": {"type": "string"},
                "budget": {"type": "integer", "default": 15000},
            },
        )
        activate_prompt_version("ai.test.render", 1)

    def test_render_prompt(self):
        result = render_prompt("ai.test.render", {"location": "Dhanmondi", "budget": 20000})
        self.assertEqual(result, "Find Dhanmondi rooms under 20000 BDT")

    def test_render_prompt_with_default(self):
        result = render_prompt("ai.test.render", {"location": "Uttara"})
        self.assertEqual(result, "Find Uttara rooms under 15000 BDT")

    def test_render_prompt_no_active_version(self):
        with self.assertRaises(ValidationError):
            render_prompt("nonexistent", {})

    def test_get_prompt_template(self):
        result = get_prompt_template("ai.test.render")
        self.assertIsNotNone(result)
        template, _variables = result
        self.assertIn("{{location}}", template)

    def test_get_prompt_template_none(self):
        result = get_prompt_template("nonexistent")
        self.assertIsNone(result)


class PromptVariableValidationTests(TestCase):
    def test_validate_clean(self):
        warnings = validate_prompt_variables(
            "Hello {{name}}, your room in {{area}}.",
            {"name": {}, "area": {}},
        )
        self.assertEqual(warnings, [])

    def test_validate_undeclared(self):
        warnings = validate_prompt_variables(
            "Hello {{name}}, your room in {{area}}.",
            {"name": {}},
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn("undeclared", warnings[0])

    def test_validate_unused(self):
        warnings = validate_prompt_variables(
            "Hello {{name}}.",
            {"name": {}, "extra": {}},
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn("unused", warnings[0])


class ExecutionLogTests(TestCase):
    def test_log_execution_basic(self):
        log = AIExecutionLog.objects.create(
            feature_key="test.log",
            provider="rules",
            status="success",
            latency_ms=42,
        )
        self.assertEqual(log.feature_key, "test.log")
        self.assertEqual(log.latency_ms, 42)

    def test_log_execution_with_prompt(self):
        log = AIExecutionLog.objects.create(
            feature_key="test.prompt.log",
            provider="rules",
            status="success",
            prompt_key="ai.test.prompt",
            prompt_version=1,
        )
        self.assertEqual(log.prompt_key, "ai.test.prompt")
        self.assertEqual(log.prompt_version, 1)


class ProviderHealthTests(TestCase):
    def test_create_health(self):
        h = ProviderHealth.objects.create(
            provider="test",
            feature_key="test.feature",
            window_start="2026-01-01T00:00:00Z",
            window_end="2026-01-01T01:00:00Z",
        )
        self.assertTrue(h.is_healthy)

    def test_str_degraded(self):
        h = ProviderHealth.objects.create(
            provider="test",
            feature_key="test.f",
            success_rate=0.5,
            is_healthy=False,
            window_start="2026-01-01T00:00:00Z",
            window_end="2026-01-01T01:00:00Z",
        )
        self.assertIn("DEGRADED", str(h))


# ---------------------------------------------------------------------------
# API Tests
# ---------------------------------------------------------------------------


class FeatureRegistryAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="admin_feature", password="pass", email="admin@f.com"
        )
        self.regular = User.objects.create_user(username="regular_feature", password="pass")
        register_feature(feature_id="api.test.feature", name="API Feature")

    def test_admin_list_features(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/ai/features/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_non_admin_403(self):
        self.client.force_authenticate(self.regular)
        r = self.client.get("/api/v1/ai/features/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_detail_feature(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/ai/features/api.test.feature/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["feature_id"], "api.test.feature")

    def test_admin_update_feature(self):
        self.client.force_authenticate(self.admin)
        r = self.client.patch(
            "/api/v1/ai/features/api.test.feature/update/",
            {"owner": "updated@rentora.com"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)


class PromptAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="admin_prompt", password="pass", email="admin@p.com"
        )
        self.regular = User.objects.create_user(username="regular_prompt", password="pass")

    def test_admin_create_prompt(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            "/api/v1/ai/prompts/",
            {
                "prompt_key": "ai.test.api.prompt",
                "name": "API Prompt",
                "template": "Find rooms in {{location}}",
                "variables": {"location": {"type": "string"}},
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["prompt_key"], "ai.test.api.prompt")

    def test_non_admin_cannot_create_prompt(self):
        self.client.force_authenticate(self.regular)
        r = self.client.post(
            "/api/v1/ai/prompts/",
            {"prompt_key": "x", "name": "x", "template": "x"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_list_prompts(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/ai/prompts/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_admin_prompt_detail(self):
        create_prompt(prompt_key="ai.test.detail", name="Detail", template="Hello")
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/ai/prompts/ai.test.detail/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["versions"]), 1)


class PromptVersionAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="admin_ver", password="pass", email="admin@v.com"
        )
        create_prompt(prompt_key="ai.test.ver.api", name="Ver API", template="v1")

    def test_create_version(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            "/api/v1/ai/prompts/ai.test.ver.api/versions/",
            {"template": "v2 template", "change_summary": "Updated"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["version"], 2)

    def test_activate_version(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            "/api/v1/ai/prompts/ai.test.ver.api/versions/1/activate/",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data["is_active"])

    def test_deactivate_version(self):
        self.client.force_authenticate(self.admin)
        self.client.post("/api/v1/ai/prompts/ai.test.ver.api/versions/1/activate/")
        r = self.client.post(
            "/api/v1/ai/prompts/ai.test.ver.api/deactivate/",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_rollback(self):
        self.client.force_authenticate(self.admin)
        # Create v2, activate it
        self.client.post(
            "/api/v1/ai/prompts/ai.test.ver.api/versions/",
            {"template": "v2"},
            format="json",
        )
        self.client.post("/api/v1/ai/prompts/ai.test.ver.api/versions/2/activate/")
        # Rollback to v1
        r = self.client.post("/api/v1/ai/prompts/ai.test.ver.api/rollback/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["version"], 1)

    def test_compare_versions(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/ai/prompts/ai.test.ver.api/compare/?v1=1&v2=1")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("v1", r.data)
        self.assertIn("v2", r.data)

    def test_compare_missing_params(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/v1/ai/prompts/ai.test.ver.api/compare/")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class TelemetryIntegrationTests(TestCase):
    def test_log_execution_with_prompt_fields(self):
        log = AIExecutionLog.objects.create(
            feature_key="test.telemetry",
            provider="rules",
            status="success",
            prompt_key="ai.test.telemetry",
            prompt_version=2,
            latency_ms=15,
        )
        self.assertEqual(log.prompt_key, "ai.test.telemetry")
        self.assertEqual(log.prompt_version, 2)
        self.assertEqual(log.latency_ms, 15)

    def test_log_execution_without_prompt(self):
        log = AIExecutionLog.objects.create(
            feature_key="test.no.prompt",
            provider="rules",
            status="success",
        )
        self.assertEqual(log.prompt_key, "")
        self.assertEqual(log.prompt_version, 0)


class ManagementCommandTests(TestCase):
    def test_register_ai_features(self):
        from django.core.management import call_command

        call_command("register_ai_features", verbosity=0)
        count = AIFeatureRegistry.objects.count()
        self.assertGreaterEqual(count, 28)  # at least 28 features seeded

    def test_register_ai_features_idempotent(self):
        from django.core.management import call_command

        call_command("register_ai_features", verbosity=0)
        count1 = AIFeatureRegistry.objects.count()
        call_command("register_ai_features", verbosity=0)
        count2 = AIFeatureRegistry.objects.count()
        self.assertEqual(count1, count2)


class CeleryTaskTests(TestCase):
    def test_purge_old_logs(self):
        from datetime import timedelta

        from django.utils import timezone

        old_log = AIExecutionLog.objects.create(
            feature_key="test.purge",
            provider="rules",
            status="success",
        )
        new_log = AIExecutionLog.objects.create(
            feature_key="test.purge.new",
            provider="rules",
            status="success",
        )
        # Backdate the old log (bypass auto_now_add)
        cutoff = timezone.now() - timedelta(days=100)
        AIExecutionLog.objects.filter(pk=old_log.pk).update(created_at=cutoff)

        result = purge_old_execution_logs()
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["deleted"], 1)
        self.assertFalse(AIExecutionLog.objects.filter(pk=old_log.pk).exists())
        self.assertTrue(AIExecutionLog.objects.filter(pk=new_log.pk).exists())

    def test_update_health(self):
        from datetime import timedelta

        from django.utils import timezone

        log = AIExecutionLog.objects.create(
            feature_key="test.health",
            provider="rules",
            status="success",
            latency_ms=50,
        )
        # Backdate the log slightly so it falls within the aggregation window
        AIExecutionLog.objects.filter(pk=log.pk).update(
            created_at=timezone.now() - timedelta(minutes=30)
        )
        updated = update_provider_health(hours=2)
        self.assertGreaterEqual(updated, 1)
        h = ProviderHealth.objects.get(provider="rules", feature_key="test.health")
        self.assertTrue(h.is_healthy)


# ===========================================================================
# Phase 18.3 — Evaluation Framework Tests
# ===========================================================================


class EvaluationMetricTests(TestCase):
    def test_create_metric(self):
        m = register_metric(
            metric_key="f1",
            name="F1 Score",
            metric_type="deterministic",
            category="classification",
        )
        self.assertEqual(m.metric_key, "f1")
        self.assertTrue(m.is_higher_better)

    def test_create_metric_idempotent(self):
        register_metric(metric_key="ndcg", name="NDCG")
        register_metric(metric_key="ndcg", name="NDCG v2")
        from .models import EvaluationMetric

        self.assertEqual(EvaluationMetric.objects.filter(metric_key="ndcg").count(), 1)

    def test_str(self):
        m = register_metric(metric_key="mae", name="MAE", metric_type="heuristic")
        self.assertIn("MAE", str(m))


class EvaluationThresholdTests(TestCase):
    def setUp(self):
        self.feature = register_feature(
            feature_id="test.threshold",
            name="Threshold Test",
            category="classification",
        )

    def test_set_threshold(self):
        register_metric(metric_key="f1", name="F1")
        t = set_threshold("test.threshold", "f1", threshold_min=0.80)
        self.assertEqual(t.threshold_min, 0.80)
        self.assertIsNone(t.threshold_max)

    def test_set_threshold_both(self):
        register_metric(metric_key="fpr", name="FPR")
        t = set_threshold("test.threshold", "fpr", threshold_min=0.0, threshold_max=0.10)
        self.assertEqual(t.threshold_min, 0.0)
        self.assertEqual(t.threshold_max, 0.10)

    def test_get_thresholds(self):
        register_metric(metric_key="f1", name="F1")
        register_metric(metric_key="precision", name="Precision")
        set_threshold("test.threshold", "f1", threshold_min=0.80)
        set_threshold("test.threshold", "precision", threshold_min=0.75)
        thresholds = get_thresholds("test.threshold")
        self.assertEqual(len(thresholds), 2)

    def test_feature_not_found(self):
        with self.assertRaises(ValueError):
            set_threshold("nonexistent.feature", "f1")

    def test_metric_not_found(self):
        register_feature(feature_id="test.no_metric", name="No Metric")
        with self.assertRaises(ValueError):
            set_threshold("test.no_metric", "nonexistent_metric")


class EvaluationDatasetTests(TestCase):
    def test_create_dataset(self):
        from .services import create_dataset

        ds = create_dataset(
            dataset_key="search.test",
            name="Search Test",
            description="A test dataset",
        )
        self.assertEqual(ds.dataset_key, "search.test")
        self.assertEqual(ds.version, 1)
        self.assertEqual(ds.status, "draft")

    def test_create_dataset_with_feature(self):
        from .services import create_dataset

        register_feature(feature_id="test.ds_feature", name="DS Feature")
        ds = create_dataset(
            dataset_key="test.feat_ds",
            name="Feature DS",
            feature_id="test.ds_feature",
        )
        self.assertIsNotNone(ds.feature)

    def test_publish_dataset(self):
        from .services import create_dataset, publish_dataset

        _ds = create_dataset(dataset_key="test.pub", name="Pub")
        published = publish_dataset("test.pub", 1)
        self.assertEqual(published.status, "published")

    def test_publish_nonexistent(self):
        from .services import publish_dataset

        with self.assertRaises(ValueError):
            publish_dataset("nonexistent", 1)

    def test_archive_dataset(self):
        from .services import archive_dataset, create_dataset, publish_dataset

        _ds = create_dataset(dataset_key="test.arch", name="Arch")
        publish_dataset("test.arch", 1)
        archived = archive_dataset("test.arch", 1)
        self.assertEqual(archived.status, "archived")

    def test_add_cases(self):
        from .services import add_cases, create_dataset

        ds = create_dataset(dataset_key="test.cases", name="Cases")
        count = add_cases(
            "test.cases",
            1,
            [
                {"input": {"query": "test"}, "expected_output": {"result": "ok"}},
                {"input": {"query": "test2"}, "expected_output": {"result": "ok2"}},
            ],
        )
        self.assertEqual(count, 2)
        ds.refresh_from_db()
        self.assertEqual(ds.sample_count, 2)

    def test_add_cases_to_published_fails(self):
        from .services import add_cases, create_dataset, publish_dataset

        create_dataset(dataset_key="test.pub_cases", name="Pub Cases")
        publish_dataset("test.pub_cases", 1)
        with self.assertRaises(ValidationError):
            add_cases("test.pub_cases", 1, [{"input": {"q": "x"}}])

    def test_create_dataset_version(self):
        from .services import add_cases, create_dataset, create_dataset_version

        _ds = create_dataset(dataset_key="test.ver", name="Versioned")
        add_cases(
            "test.ver",
            1,
            [
                {"input": {"q": "a"}},
                {"input": {"q": "b"}},
            ],
        )
        ds2 = create_dataset_version("test.ver", name="Version 2")
        self.assertEqual(ds2.version, 2)
        self.assertEqual(ds2.sample_count, 2)

    def test_get_dataset(self):
        from .services import create_dataset, get_dataset

        create_dataset(dataset_key="test.get", name="Get")
        ds = get_dataset("test.get")
        self.assertIsNotNone(ds)
        self.assertEqual(ds.dataset_key, "test.get")


class EvaluatorTests(TestCase):
    def test_search_precision_at_k(self):
        from .evaluators import _precision_at_k

        result = _precision_at_k(
            "query",
            ["a", "b", "c"],
            ["a", "b", "d"],
            {"k": 3},
        )
        self.assertAlmostEqual(result["precision_at_k"], 2 / 3, places=2)

    def test_search_ndcg(self):
        from .evaluators import _ndcg

        result = _ndcg(
            "query",
            ["a", "b", "c"],
            ["a", "b"],
            {"k": 3},
        )
        self.assertIn("ndcg", result)
        self.assertGreater(result["ndcg"], 0)

    def test_search_mrr(self):
        from .evaluators import _mrr

        result = _mrr(
            "query",
            ["x", "y", "a"],
            ["a"],
            {},
        )
        self.assertAlmostEqual(result["mrr"], 1 / 3, places=2)

    def test_exact_match(self):
        from .evaluators import _exact_match

        self.assertEqual(_exact_match("x", "hello", "hello", {})["exact_match"], 1.0)
        self.assertEqual(_exact_match("x", "hello", "world", {})["exact_match"], 0.0)

    def test_f1_score(self):
        from .evaluators import _f1_score

        result = _f1_score("x", "fraud", "fraud", {})
        self.assertEqual(result["f1"], 1.0)
        result = _f1_score("x", "safe", "fraud", {})
        self.assertEqual(result["f1"], 0.0)

    def test_false_positive_rate(self):
        from .evaluators import _false_positive_rate

        result = _false_positive_rate("x", "fraud", "safe", {})
        self.assertEqual(result["false_positive_rate"], 1.0)
        result = _false_positive_rate("x", "safe", "safe", {})
        self.assertEqual(result["false_positive_rate"], 0.0)

    def test_llm_task_success(self):
        from .evaluators import _llm_task_success

        result = _llm_task_success("q", "answer", "answer", {})
        self.assertEqual(result["task_success"], 1.0)
        result = _llm_task_success("q", None, "answer", {})
        self.assertEqual(result["task_success"], 0.0)

    def test_evaluate_case_dispatch(self):
        from .evaluators import evaluate_case

        result = evaluate_case(
            "general.exact_match",
            "input",
            "input",
            "input",
        )
        self.assertEqual(result.get("exact_match"), 1.0)

    def test_evaluate_case_unknown_category(self):
        from .evaluators import evaluate_case

        result = evaluate_case("nonexistent.category", "a", "b")
        self.assertEqual(result, {})


class EvaluationRunTests(TestCase):
    def setUp(self):
        self.feature = register_feature(
            feature_id="test.eval_run",
            name="Eval Run Test",
            category="classification",
        )
        from .services import add_cases, create_dataset

        create_dataset(
            dataset_key="test.eval_ds",
            name="Eval DS",
            feature_id="test.eval_run",
        )
        add_cases(
            "test.eval_ds",
            1,
            [
                {"input": {"text": "hello"}, "expected_output": {"label": "positive"}},
                {"input": {"text": "bad"}, "expected_output": {"label": "negative"}},
            ],
        )

    def test_create_run(self):
        from .services import create_evaluation_run

        run = create_evaluation_run(
            feature_id="test.eval_run",
            dataset_key="test.eval_ds",
            model_name="test_model",
            provider="rules",
        )
        self.assertEqual(run.status, "pending")
        self.assertIsNotNone(run.run_key)

    def test_execute_run(self):
        from .services import create_evaluation_run, execute_evaluation_run

        run = create_evaluation_run(
            feature_id="test.eval_run",
            dataset_key="test.eval_ds",
        )
        result = execute_evaluation_run(run.pk)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["total_cases"], 2)
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertGreater(run.duration_ms, 0)

    def test_cancel_run(self):
        from .services import cancel_evaluation_run, create_evaluation_run

        run = create_evaluation_run(
            feature_id="test.eval_run",
            dataset_key="test.eval_ds",
        )
        self.assertTrue(cancel_evaluation_run(run.pk))
        run.refresh_from_db()
        self.assertEqual(run.status, "cancelled")

    def test_execute_nonexistent_run(self):
        from .services import execute_evaluation_run

        result = execute_evaluation_run(99999)
        self.assertEqual(result["status"], "error")

    def test_run_with_thresholds(self):
        register_metric(metric_key="accuracy", name="Accuracy")
        set_threshold("test.eval_run", "accuracy", threshold_min=0.5)
        from .services import create_evaluation_run, execute_evaluation_run

        run = create_evaluation_run(
            feature_id="test.eval_run",
            dataset_key="test.eval_ds",
        )
        result = execute_evaluation_run(run.pk)
        self.assertEqual(result["status"], "completed")


class ComparisonTests(TestCase):
    def setUp(self):
        self.feature = register_feature(
            feature_id="test.compare",
            name="Compare Test",
            category="classification",
        )
        from .services import (
            add_cases,
            create_dataset,
            create_evaluation_run,
            execute_evaluation_run,
        )

        create_dataset(
            dataset_key="test.cmp_ds",
            name="Compare DS",
            feature_id="test.compare",
        )
        add_cases(
            "test.cmp_ds",
            1,
            [
                {"input": {"text": "a"}, "expected_output": {"label": "pos"}},
            ],
        )
        run_a = create_evaluation_run(
            feature_id="test.compare",
            dataset_key="test.cmp_ds",
            model_name="model_a",
        )
        execute_evaluation_run(run_a.pk)
        run_b = create_evaluation_run(
            feature_id="test.compare",
            dataset_key="test.cmp_ds",
            model_name="model_b",
        )
        execute_evaluation_run(run_b.pk)
        self.run_a = run_a
        self.run_b = run_b

    def test_compare_runs(self):
        from .services import compare_runs

        result = compare_runs(self.run_a.pk, self.run_b.pk)
        self.assertIn("run_a", result)
        self.assertIn("run_b", result)
        self.assertIn("overall_winner", result)

    def test_compare_runs_not_found(self):
        from .services import compare_runs

        result = compare_runs(99999, 99998)
        self.assertIn("error", result)


class RegressionDetectionTests(TestCase):
    def setUp(self):
        self.feature = register_feature(
            feature_id="test.regress",
            name="Regress Test",
            category="classification",
        )
        register_metric(metric_key="accuracy", name="Accuracy", is_higher_better=True)
        set_threshold("test.regress", "accuracy", threshold_min=0.5)

    def test_check_regression_no_threshold_breach(self):
        from .services import (
            add_cases,
            check_regression,
            create_dataset,
            create_evaluation_run,
            execute_evaluation_run,
        )

        create_dataset(
            dataset_key="test.reg_ds",
            name="Reg DS",
            feature_id="test.regress",
        )
        add_cases(
            "test.reg_ds",
            1,
            [
                {"input": {"text": "a"}, "expected_output": {"label": "pos"}},
            ],
        )
        run = create_evaluation_run(
            feature_id="test.regress",
            dataset_key="test.reg_ds",
        )
        execute_evaluation_run(run.pk)
        result = check_regression(run.pk)
        self.assertFalse(result["has_regression"])

    def test_check_regression_not_completed(self):
        from .services import check_regression, create_dataset, create_evaluation_run

        create_dataset(
            dataset_key="test.reg_ds2",
            name="Reg DS2",
            feature_id="test.regress",
        )
        run = create_evaluation_run(
            feature_id="test.regress",
            dataset_key="test.reg_ds2",
        )
        result = check_regression(run.pk)
        self.assertIn("error", result)


class TaskTests(TestCase):
    def test_execute_evaluation_run_task(self):
        from .services import add_cases, create_dataset, create_evaluation_run
        from .tasks import execute_evaluation_run_task

        register_feature(feature_id="test.task", name="Task Test")
        create_dataset(
            dataset_key="test.task_ds",
            name="Task DS",
            feature_id="test.task",
        )
        add_cases(
            "test.task_ds",
            1,
            [
                {"input": {"q": "test"}, "expected_output": {"a": "ok"}},
            ],
        )
        run = create_evaluation_run(
            feature_id="test.task",
            dataset_key="test.task_ds",
        )
        result = execute_evaluation_run_task(run.pk)
        self.assertEqual(result["status"], "completed")

    def test_cancel_stale_evaluation_runs(self):
        from .tasks import cancel_stale_evaluation_runs

        result = cancel_stale_evaluation_runs()
        self.assertEqual(result["status"], "success")


class EvaluationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = get_user_model().objects.create_user(
            username="eval_admin",
            email="eval_admin@test.com",
            password="test12345",
            is_staff=True,
        )
        self.client.force_authenticate(user=self.admin)

    def test_metric_list(self):
        register_metric(metric_key="f1", name="F1")
        resp = self.client.get("/api/v1/ai/eval/metrics/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_dataset_list(self):
        resp = self.client.get("/api/v1/ai/eval/datasets/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_dataset_create(self):
        resp = self.client.post(
            "/api/v1/ai/eval/datasets/",
            {
                "dataset_key": "api.test_ds",
                "name": "API Test DS",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_run_list(self):
        resp = self.client.get("/api/v1/ai/eval/runs/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_run_create(self):
        register_feature(feature_id="test.api_run", name="API Run Test")
        from .services import add_cases, create_dataset

        create_dataset(
            dataset_key="test.api_ds",
            name="API DS",
            feature_id="test.api_run",
        )
        add_cases(
            "test.api_ds",
            1,
            [
                {"input": {"q": "x"}, "expected_output": {"a": "y"}},
            ],
        )
        resp = self.client.post(
            "/api/v1/ai/eval/runs/",
            {
                "feature_id": "test.api_run",
                "dataset_key": "test.api_ds",
                "model_name": "test_model",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_threshold_list(self):
        resp = self.client.get("/api/v1/ai/eval/thresholds/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_unauthenticated_access_denied(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get("/api/v1/ai/eval/metrics/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
