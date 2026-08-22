import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ModelVersion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Model identifier (e.g. review_trust, photo_geo, scam_graph).",
                        max_length=100,
                    ),
                ),
                (
                    "version",
                    models.CharField(
                        help_text="Version string (e.g. 1.0.0, 2026-08-22).",
                        max_length=50,
                    ),
                ),
                ("description", models.TextField(blank=True, default="")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("deprecated", "Deprecated"),
                            ("experimental", "Experimental"),
                        ],
                        default="experimental",
                        max_length=16,
                    ),
                ),
                ("training_date", models.DateTimeField(blank=True, null=True)),
                (
                    "metrics",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Performance metrics at training time (accuracy, precision, recall, f1, etc.).",
                    ),
                ),
                (
                    "artifacts_path",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Path to model artifacts (if self-hosted). Empty for provider-based models.",
                        max_length=500,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["name", "-version"],
            },
        ),
        migrations.CreateModel(
            name="DriftMetric",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "metric_name",
                    models.CharField(
                        help_text="Metric identifier (e.g. accuracy, precision, recall, f1, latency_p95).",
                        max_length=100,
                    ),
                ),
                (
                    "value",
                    models.FloatField(
                        help_text="Measured value for this metric in the time window."
                    ),
                ),
                (
                    "baseline_value",
                    models.FloatField(
                        blank=True,
                        help_text="Training-time baseline for comparison.",
                        null=True,
                    ),
                ),
                (
                    "threshold_min",
                    models.FloatField(
                        blank=True,
                        help_text="Lower bound — breached if value drops below this.",
                        null=True,
                    ),
                ),
                (
                    "threshold_max",
                    models.FloatField(
                        blank=True,
                        help_text="Upper bound — breached if value exceeds this.",
                        null=True,
                    ),
                ),
                (
                    "threshold_breached",
                    models.BooleanField(
                        default=False,
                        help_text="True if value is outside the acceptable range.",
                    ),
                ),
                (
                    "window_start",
                    models.DateTimeField(help_text="Start of the measurement window."),
                ),
                (
                    "window_end",
                    models.DateTimeField(help_text="End of the measurement window."),
                ),
                (
                    "sample_count",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Number of data points in this window.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "model_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="drift_metrics",
                        to="ml_models.modelversion",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="RetrainRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "reason",
                    models.TextField(
                        help_text="Why this retrain was triggered (drift alert, manual request, scheduled)."
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Admin notes or failure details.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "model_version",
                    models.ForeignKey(
                        blank=True,
                        help_text="The model version to retrain (null for brand-new model training).",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="retrain_requests",
                        to="ml_models.modelversion",
                    ),
                ),
                (
                    "triggered_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="retrain_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="driftmetric",
            index=models.Index(
                fields=["model_version", "metric_name", "created_at"],
                name="drift_metric_lookup_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="driftmetric",
            index=models.Index(
                fields=["threshold_breached", "created_at"],
                name="drift_breached_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="modelversion",
            constraint=models.UniqueConstraint(
                fields=("name", "version"), name="ml_model_version_unique"
            ),
        ),
    ]
