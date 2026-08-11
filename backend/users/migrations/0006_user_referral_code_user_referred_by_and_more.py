# Backfills unique referral codes + wishlist share tokens for existing rows,
# then enforces uniqueness. (SQLite evaluates a callable default once per
# ALTER TABLE, so the naive AddField(unique=True, default=uuid.uuid4) would
# give every existing user the same token — this two-step version avoids it.)

import secrets
import string
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_ALPHABET = string.ascii_uppercase + string.digits


def backfill_tokens(apps, schema_editor):
    User = apps.get_model(settings.AUTH_USER_MODEL)
    used_codes = set(User.objects.exclude(referral_code="").values_list("referral_code", flat=True))
    used_tokens = set(User.objects.values_list("wishlist_share_token", flat=True))

    for user in User.objects.all().iterator():
        changed = False
        if not user.referral_code:
            code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
            while code in used_codes:
                code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
            user.referral_code = code
            used_codes.add(code)
            changed = True
        if not user.wishlist_share_token or user.wishlist_share_token in used_tokens:
            token = uuid.uuid4()
            while token in used_tokens:
                token = uuid.uuid4()
            user.wishlist_share_token = token
            used_tokens.add(token)
            changed = True
        if changed:
            user.save(update_fields=["referral_code", "wishlist_share_token"])


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0005_kycdocument"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="referral_code",
            field=models.CharField(
                blank=True, editable=False, max_length=12, null=True, unique=True
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="referred_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="referrals",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="wishlist_share_token",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(backfill_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="wishlist_share_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=False, unique=True),
        ),
    ]
