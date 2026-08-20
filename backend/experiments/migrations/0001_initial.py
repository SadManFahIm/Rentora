from django.db import migrations, models

import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Experiment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("key", models.CharField(max_length=128, unique=True)),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("owner", models.CharField(blank=True, default="", max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("active", "Active"),
                            ("completed", "Completed"),
                            ("archived", "Archived"),
                        ],
                        default="draft",
                        max_length=16,
                    ),
                ),
                ("traffic_allocation", models.PositiveIntegerField(default=100)),
                ("start_at", models.DateTimeField(blank=True, null=True)),
                ("end_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["key"]},
        ),
        migrations.CreateModel(
            name="ExperimentVariant",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("key", models.CharField(max_length=64)),
                ("label", models.CharField(blank=True, default="", max_length=200)),
                ("weight", models.PositiveIntegerField(default=1)),
                ("is_control", models.BooleanField(default=False)),
                (
                    "experiment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="variants",
                        to="experiments.experiment",
                    ),
                ),
            ],
            options={"ordering": ["experiment_id", "id"]},
        ),
        migrations.CreateModel(
            name="ExperimentExposure",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("assignee_key", models.CharField(db_index=True, max_length=128)),
                ("context", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "experiment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="exposures",
                        to="experiments.experiment",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="experiment_exposures",
                        to="users.user",
                    ),
                ),
                (
                    "variant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="exposures",
                        to="experiments.experimentvariant",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ExperimentAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("assignee_key", models.CharField(db_index=True, max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "experiment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignments",
                        to="experiments.experiment",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="experiment_assignments",
                        to="users.user",
                    ),
                ),
                (
                    "variant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignments",
                        to="experiments.experimentvariant",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="experimentvariant",
            constraint=models.UniqueConstraint(
                fields=("experiment", "key"), name="variant_experiment_key_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="experimentassignment",
            constraint=models.UniqueConstraint(
                fields=("experiment", "assignee_key"), name="assignment_experiment_key_unique"
            ),
        ),
        migrations.AddIndex(
            model_name="experimentexposure",
            index=models.Index(
                fields=["experiment", "assignee_key"], name="exposure_experiment_user_idx"
            ),
        ),
    ]
