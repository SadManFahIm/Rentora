from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ImageVariant",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("entity_type", models.CharField(db_index=True, max_length=64)),
                ("entity_id", models.PositiveBigIntegerField()),
                ("size_key", models.CharField(max_length=32)),
                ("width", models.PositiveIntegerField()),
                ("height", models.PositiveIntegerField()),
                ("file", models.FileField(upload_to="image_variants/%Y/%m/")),
                ("format", models.CharField(default="webp", max_length=16)),
                (
                    "source_hash",
                    models.CharField(blank=True, db_index=True, default="", max_length=64),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["entity_type", "entity_id", "size_key"]},
        ),
        migrations.AddIndex(
            model_name="imagevariant",
            index=models.Index(
                fields=["entity_type", "entity_id"], name="image_variant_entity_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="imagevariant",
            constraint=models.UniqueConstraint(
                fields=("entity_type", "entity_id", "size_key"),
                name="image_variant_entity_size_unique",
            ),
        ),
    ]
