from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="FeatureFlag",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("key", models.CharField(max_length=128, unique=True)),
                ("label", models.CharField(blank=True, default="", max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("owner", models.CharField(blank=True, default="", max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("enabled", "Enabled"),
                            ("disabled", "Disabled"),
                            ("partial", "Partial rollout"),
                        ],
                        default="disabled",
                        max_length=16,
                    ),
                ),
                ("rollout_percentage", models.PositiveIntegerField(default=0)),
                ("environments", models.JSONField(blank=True, default=list)),
                ("roles", models.JSONField(blank=True, default=list)),
                ("user_ids", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("cleanup_plan", models.CharField(blank=True, default="", max_length=500)),
            ],
            options={"ordering": ["key"]},
        ),
    ]
