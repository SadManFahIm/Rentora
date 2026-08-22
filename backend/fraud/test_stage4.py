"""Phase 17 -- Stage 4: KYC Liveness + Face-Match Tests."""

import io
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from fraud.services.provider_base import (
    FailureType,
    Registry,
)
from users.face_match_provider import (
    RulesFaceMatchProvider,
    get_face_match_provider,
    run_face_match,
)
from users.liveness_provider import (
    RulesLivenessProvider,
    get_liveness_provider,
    run_liveness_check,
)
from users.models import LivenessChallenge, LivenessConsent, TenantVerification, User


def _create_user(**kwargs):
    defaults = {"username": "testuser", "email": "test@example.com"}
    defaults.update(kwargs)
    return User.objects.create_user(**defaults, password="testpass123")


def _make_selfie_bytes():
    return b"\xff\xd8\xff\xe0" + b"\x00" * 200 + b"\xff\xd9"


def _make_selfie(name="selfie.jpg"):
    from PIL import Image

    img = Image.new("RGB", (100, 100), color=(200, 150, 100))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


def _force_set_created(obj, dt):
    type(obj).objects.filter(pk=obj.pk).update(created_at=dt)


# -- Model Tests --


class LivenessChallengeModelTest(TestCase):
    def test_create_challenge(self):
        user = _create_user()
        challenge = LivenessChallenge.objects.create(
            user=user,
            challenge_type=LivenessChallenge.ChallengeType.BLINK,
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        self.assertEqual(challenge.status, LivenessChallenge.Status.PENDING)
        self.assertFalse(challenge.is_expired)

    def test_is_expired_true(self):
        user = _create_user()
        challenge = LivenessChallenge.objects.create(
            user=user,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertTrue(challenge.is_expired)

    def test_is_expired_none(self):
        user = _create_user()
        challenge = LivenessChallenge.objects.create(user=user, expires_at=None)
        self.assertFalse(challenge.is_expired)

    def test_str(self):
        user = _create_user()
        challenge = LivenessChallenge.objects.create(user=user)
        self.assertIn(str(user.pk), str(challenge))


class LivenessConsentModelTest(TestCase):
    def test_create_consent(self):
        user = _create_user()
        consent = LivenessConsent.objects.create(
            user=user,
            consent_type=LivenessConsent.ConsentType.LIVENESS,
            granted=True,
            granted_at=timezone.now(),
        )
        self.assertTrue(consent.granted)
        self.assertIn("granted", str(consent))

    def test_unique_together(self):
        from django.db import IntegrityError

        user = _create_user()
        LivenessConsent.objects.create(
            user=user,
            consent_type=LivenessConsent.ConsentType.LIVENESS,
        )
        with self.assertRaises(IntegrityError):
            LivenessConsent.objects.create(
                user=user,
                consent_type=LivenessConsent.ConsentType.LIVENESS,
            )


# -- Provider Tests --


class LivenessProviderTest(TestCase):
    def setUp(self):
        Registry._providers.setdefault("liveness", {})
        Registry._providers["liveness"]["rules"] = RulesLivenessProvider

    def test_rules_provider_pass(self):
        provider = RulesLivenessProvider()
        result = provider.run(selfie_bytes=_make_selfie_bytes())
        self.assertTrue(result.success)
        self.assertEqual(result.provider, "rules")
        self.assertGreater(result.confidence, 0)

    def test_rules_provider_no_selfie(self):
        provider = RulesLivenessProvider()
        result = provider.run()
        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, FailureType.USER_FAILURE)

    def test_rules_provider_tiny_selfie(self):
        provider = RulesLivenessProvider()
        result = provider.run(selfie_bytes=b"\xff\xd8\xff\xd9")
        self.assertFalse(result.success)

    def test_registry_resolve_empty(self):
        cls = get_liveness_provider()
        self.assertIsNone(cls)

    @override_settings(KYC_LIVENESS_PROVIDER="rules")
    def test_registry_resolve_rules(self):
        cls = get_liveness_provider()
        self.assertIsNotNone(cls)
        self.assertEqual(cls.name, "rules")

    @override_settings(KYC_LIVENESS_PROVIDER="nonexistent")
    def test_registry_resolve_missing(self):
        cls = get_liveness_provider()
        self.assertIsNone(cls)

    def test_run_liveness_check_no_provider(self):
        result = run_liveness_check(user=_create_user(), challenge_type="blink", selfie_bytes=b"")
        self.assertFalse(result.success)

    @override_settings(KYC_LIVENESS_PROVIDER="rules")
    def test_run_liveness_check_rules(self):
        result = run_liveness_check(
            user=_create_user(),
            challenge_type="blink",
            selfie_bytes=_make_selfie_bytes(),
        )
        self.assertTrue(result.success)
        self.assertEqual(result.provider, "rules")


class FaceMatchProviderTest(TestCase):
    def setUp(self):
        Registry._providers.setdefault("face_match", {})
        Registry._providers["face_match"]["rules"] = RulesFaceMatchProvider

    def test_rules_provider_pass(self):
        provider = RulesFaceMatchProvider()
        result = provider.run(document_path="", selfie_bytes=_make_selfie_bytes())
        self.assertTrue(result.success)
        self.assertEqual(result.provider, "rules")

    def test_rules_provider_no_selfie(self):
        provider = RulesFaceMatchProvider()
        result = provider.run(document_path="")
        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, FailureType.USER_FAILURE)

    def test_rules_provider_missing_doc(self):
        provider = RulesFaceMatchProvider()
        result = provider.run(
            document_path="/nonexistent/file.jpg",
            selfie_bytes=_make_selfie_bytes(),
        )
        self.assertFalse(result.success)

    def test_registry_resolve_empty(self):
        cls = get_face_match_provider()
        self.assertIsNone(cls)

    @override_settings(KYC_FACE_MATCH_PROVIDER="rules")
    def test_registry_resolve_rules(self):
        cls = get_face_match_provider()
        self.assertIsNotNone(cls)
        self.assertEqual(cls.name, "rules")

    def test_run_face_match_no_provider(self):
        result = run_face_match(user=_create_user(), document_path="", selfie_bytes=b"")
        self.assertFalse(result.success)

    @override_settings(KYC_FACE_MATCH_PROVIDER="rules")
    def test_run_face_match_rules(self):
        result = run_face_match(
            user=_create_user(),
            document_path="",
            selfie_bytes=_make_selfie_bytes(),
        )
        self.assertTrue(result.success)


# -- OCR Confidence Threshold Tests --


class OcrConfidenceThresholdTest(TestCase):
    def test_high_above_medium(self):
        from users.kyc_ocr import ocr_score_boost

        extracted = {"nid_number": "12345678901234567", "confidence": "high"}
        with override_settings(KYC_OCR_MIN_CONFIDENCE="medium"):
            self.assertEqual(ocr_score_boost(extracted), 5)

    def test_medium_at_medium(self):
        from users.kyc_ocr import ocr_score_boost

        extracted = {"nid_number": "12345678901234567", "confidence": "medium"}
        with override_settings(KYC_OCR_MIN_CONFIDENCE="medium"):
            self.assertEqual(ocr_score_boost(extracted), 5)

    def test_low_below_medium(self):
        from users.kyc_ocr import ocr_score_boost

        extracted = {"nid_number": "12345678901234567", "confidence": "low"}
        with override_settings(KYC_OCR_MIN_CONFIDENCE="medium"):
            self.assertEqual(ocr_score_boost(extracted), 0)

    def test_high_at_high(self):
        from users.kyc_ocr import ocr_score_boost

        extracted = {"nid_number": "12345678901234567", "confidence": "high"}
        with override_settings(KYC_OCR_MIN_CONFIDENCE="high"):
            self.assertEqual(ocr_score_boost(extracted), 5)

    def test_medium_below_high(self):
        from users.kyc_ocr import ocr_score_boost

        extracted = {"nid_number": "12345678901234567", "confidence": "medium"}
        with override_settings(KYC_OCR_MIN_CONFIDENCE="high"):
            self.assertEqual(ocr_score_boost(extracted), 0)

    def test_none_returns_zero(self):
        from users.kyc_ocr import ocr_score_boost

        self.assertEqual(ocr_score_boost(None), 0)

    def test_no_nid_returns_zero(self):
        from users.kyc_ocr import ocr_score_boost

        self.assertEqual(ocr_score_boost({"confidence": "high"}), 0)


# -- API Endpoint Tests --


class LivenessInitViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)

    def test_init_challenge(self):
        response = self.client.post(
            "/api/v1/users/kyc/liveness/init/",
            {"challenge_type": "blink"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "pending")
        self.assertIn("expires_at", response.data)

    def test_init_default_type(self):
        response = self.client.post(
            "/api/v1/users/kyc/liveness/init/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_unauthenticated(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/v1/users/kyc/liveness/init/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class LivenessVerifyViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        LivenessConsent.objects.create(
            user=self.user,
            consent_type=LivenessConsent.ConsentType.LIVENESS,
            granted=True,
            granted_at=timezone.now(),
        )
        Registry._providers.setdefault("liveness", {})
        Registry._providers["liveness"]["rules"] = RulesLivenessProvider

    @override_settings(KYC_LIVENESS_PROVIDER="rules")
    def test_verify_success(self):
        challenge = LivenessChallenge.objects.create(
            user=self.user,
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        response = self.client.post(
            "/api/v1/users/kyc/liveness/verify/",
            {"challenge_id": challenge.pk, "selfie": _make_selfie()},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "passed")

    def test_verify_no_consent(self):
        LivenessConsent.objects.filter(user=self.user).delete()
        challenge = LivenessChallenge.objects.create(
            user=self.user,
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        response = self.client.post(
            "/api/v1/users/kyc/liveness/verify/",
            {"challenge_id": challenge.pk, "selfie": _make_selfie()},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_verify_expired(self):
        challenge = LivenessChallenge.objects.create(
            user=self.user,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        response = self.client.post(
            "/api/v1/users/kyc/liveness/verify/",
            {"challenge_id": challenge.pk, "selfie": _make_selfie()},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_already_completed(self):
        challenge = LivenessChallenge.objects.create(
            user=self.user,
            status=LivenessChallenge.Status.PASSED,
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        response = self.client.post(
            "/api/v1/users/kyc/liveness/verify/",
            {"challenge_id": challenge.pk, "selfie": _make_selfie()},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_not_found(self):
        response = self.client.post(
            "/api/v1/users/kyc/liveness/verify/",
            {"challenge_id": 99999, "selfie": _make_selfie()},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(KYC_LIVENESS_PROVIDER="rules")
    def test_verify_updates_challenge(self):
        challenge = LivenessChallenge.objects.create(
            user=self.user,
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        response = self.client.post(
            "/api/v1/users/kyc/liveness/verify/",
            {"challenge_id": challenge.pk, "selfie": _make_selfie()},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, LivenessChallenge.Status.PASSED)
        self.assertIsNotNone(challenge.completed_at)
        self.assertEqual(challenge.provider_name, "rules")


class LivenessStatusViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)

    def test_no_challenge(self):
        response = self.client.get("/api/v1/users/kyc/liveness/status/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_status(self):
        LivenessChallenge.objects.create(user=self.user, status="passed")
        response = self.client.get("/api/v1/users/kyc/liveness/status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "passed")


class FaceMatchViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        LivenessConsent.objects.create(
            user=self.user,
            consent_type=LivenessConsent.ConsentType.FACE_MATCH,
            granted=True,
            granted_at=timezone.now(),
        )
        Registry._providers.setdefault("face_match", {})
        Registry._providers["face_match"]["rules"] = RulesFaceMatchProvider

    def test_no_consent(self):
        LivenessConsent.objects.filter(user=self.user).delete()
        response = self.client.post(
            "/api/v1/users/kyc/face-match/",
            {"selfie": _make_selfie()},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_liveness_passed(self):
        response = self.client.post(
            "/api/v1/users/kyc/face-match/",
            {"selfie": _make_selfie()},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_kyc_document(self):
        LivenessChallenge.objects.create(
            user=self.user,
            status=LivenessChallenge.Status.PASSED,
        )
        response = self.client.post(
            "/api/v1/users/kyc/face-match/",
            {"selfie": _make_selfie()},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(KYC_FACE_MATCH_PROVIDER="rules")
    def test_face_match_success(self):
        LivenessChallenge.objects.create(
            user=self.user,
            status=LivenessChallenge.Status.PASSED,
        )
        from django.core.files.base import ContentFile

        verification = TenantVerification.objects.create(
            user=self.user,
            doc_type="nid",
        )
        img_content = b"\xff\xd8\xff\xe0" + b"\x00" * 200 + b"\xff\xd9"
        verification.file.save("test_nid.jpg", ContentFile(img_content), save=True)

        response = self.client.post(
            "/api/v1/users/kyc/face-match/",
            {"selfie": _make_selfie()},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["face_match_status"], "passed")

        verification.file.delete(save=False)
        verification.delete()


class LivenessConsentViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)

    def test_get_empty(self):
        response = self.client.get("/api/v1/users/kyc/consent/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_grant_consent(self):
        response = self.client.post(
            "/api/v1/users/kyc/consent/",
            {"consent_type": "liveness", "granted": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["granted"])
        self.assertIsNotNone(response.data["granted_at"])

    def test_revoke_consent(self):
        LivenessConsent.objects.create(
            user=self.user,
            consent_type=LivenessConsent.ConsentType.LIVENESS,
            granted=True,
            granted_at=timezone.now(),
        )
        response = self.client.post(
            "/api/v1/users/kyc/consent/",
            {"consent_type": "liveness", "granted": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["granted"])
        self.assertIsNotNone(response.data["revoked_at"])

    def test_list_consents(self):
        LivenessConsent.objects.create(
            user=self.user,
            consent_type=LivenessConsent.ConsentType.LIVENESS,
            granted=True,
            granted_at=timezone.now(),
        )
        response = self.client.get("/api/v1/users/kyc/consent/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


# -- Task Tests --


class PurgeExpiredLivenessTaskTest(TestCase):
    def test_purge_old_challenges(self):
        from fraud.tasks import purge_expired_liveness

        user = _create_user()
        old = LivenessChallenge.objects.create(
            user=user,
            status=LivenessChallenge.Status.PASSED,
        )
        _force_set_created(old, timezone.now() - timedelta(days=100))
        recent = LivenessChallenge.objects.create(
            user=user,
            status=LivenessChallenge.Status.PENDING,
        )

        result = purge_expired_liveness()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["deleted"], 1)
        self.assertFalse(LivenessChallenge.objects.filter(pk=old.pk).exists())
        self.assertTrue(LivenessChallenge.objects.filter(pk=recent.pk).exists())

    def test_purge_nothing(self):
        from fraud.tasks import purge_expired_liveness

        result = purge_expired_liveness()
        self.assertEqual(result["deleted"], 0)
