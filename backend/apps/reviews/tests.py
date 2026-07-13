import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.core.files.storage import InMemoryStorage, storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from apps.reviews.models import PlatformReview, ReviewMessage


class RemoteMemoryStorage(InMemoryStorage):
    """模擬可寫入、但 URL 位於獨立 media origin 的 object storage。"""

    def url(self, name):
        return f"https://media.invalid/{name}"


class MediaStorageSettingsTests(SimpleTestCase):
    def _settings_process(self, *, bucket: str):
        env = os.environ.copy()
        env.update(
            {
                "DJANGO_SECRET_KEY": "test-only-django-secret-with-at-least-32-bytes",
                "PASSWORD_RESET_TOKEN_PEPPER": "test-only-reset-pepper-with-at-least-32-bytes",
                "ARGUS_PAYMENT_MODE": "disabled",
                "ARGUS_MEDIA_STORAGE_BACKEND": "storages.backends.s3.S3Storage",
                "ARGUS_MEDIA_BUCKET": bucket,
            }
        )
        return subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from config import settings; "
                    "assert settings.ARGUS_MEDIA_STORAGE_BACKEND == "
                    "'storages.backends.s3.S3Storage'; "
                    "assert settings.AWS_STORAGE_BUCKET_NAME == 'test-bucket'"
                ),
            ],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_s3_storage_requires_bucket(self):
        result = self._settings_process(bucket="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("S3 media storage requires ARGUS_MEDIA_BUCKET", result.stderr)

    def test_s3_storage_maps_bucket(self):
        result = self._settings_process(bucket="test-bucket")
        self.assertEqual(result.returncode, 0, result.stderr)


def _make_user(username, **extra):
    defaults = {
        "email": f"{username}@example.com",
        "password": "safe-test-password",
    }
    defaults.update(extra)
    return get_user_model().objects.create_user(username=username, **defaults)


def _png_bytes():
    """產生 1x1 PNG bytes，給 ImageField 測試用。"""
    img = Image.new("RGB", (1, 1), color="red")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _image_bytes(*, size=(1, 1), image_format="PNG", exif=None):
    image = Image.new("RGB", size, color="red")
    buffer = BytesIO()
    save_kwargs = {"exif": exif} if exif is not None else {}
    image.save(buffer, format=image_format, **save_kwargs)
    return buffer.getvalue()


class PlatformReviewModelTests(APITestCase):
    def test_one_review_per_user(self):
        user = _make_user("alice")
        PlatformReview.objects.create(user=user, rating=5, comment="很棒！")
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlatformReview.objects.create(user=user, rating=4)


class PlatformReviewAPITests(APITestCase):
    def setUp(self):
        self.user = _make_user("bob", first_name="鮑伯", last_name="王")

    def test_create_review_via_post(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            reverse("reviews-mine"),
            {"rating": 5, "comment": "Argus 太強了"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        review = PlatformReview.objects.get(user=self.user)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, "Argus 太強了")

    def test_second_post_rejected_with_400(self):
        """使用者只能評分一次；第二次 POST 回 400，引導改用 messages 補充。"""
        self.client.force_authenticate(self.user)
        self.client.post(
            reverse("reviews-mine"), {"rating": 3, "comment": "還行"}, format="json",
        )
        response = self.client.post(
            reverse("reviews-mine"), {"rating": 5, "comment": "改主意"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # rating 不變
        review = PlatformReview.objects.get(user=self.user)
        self.assertEqual(review.rating, 3)

    def test_rating_must_be_within_range(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            reverse("reviews-mine"), {"rating": 10, "comment": "破表"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_my_review_returns_404_when_not_yet_written(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse("reviews-mine"))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_reviews_is_public(self):
        carol = _make_user("carol")
        PlatformReview.objects.create(user=carol, rating=4, comment="不錯")
        response = self.client.get(reverse("reviews-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["reviews"]), 1)
        self.assertFalse(response.data["reviews"][0]["is_mine"])

    def test_is_mine_flag_correct_for_logged_in_user(self):
        self.client.force_authenticate(self.user)
        PlatformReview.objects.create(user=self.user, rating=5)
        response = self.client.get(reverse("reviews-list"))
        self.assertTrue(response.data["reviews"][0]["is_mine"])


class ReviewMessageTests(APITestCase):
    def setUp(self):
        self.user = _make_user("eve")
        self.review = PlatformReview.objects.create(user=self.user, rating=4)
        self.client.force_authenticate(self.user)
        self.url = reverse("reviews-create-message", args=[self.review.id])

    def test_user_can_post_multiple_messages(self):
        for i in range(3):
            response = self.client.post(
                self.url, {"body": f"留言 {i}"}, format="multipart",
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.review.messages.count(), 3)

    def test_message_requires_body_or_image(self):
        response = self.client.post(self.url, {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_message_can_attach_image(self):
        image = SimpleUploadedFile(
            "issue.png", _png_bytes(), content_type="image/png",
        )
        response = self.client.post(
            self.url,
            {"body": "我遇到這個畫面", "image": image},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        msg = ReviewMessage.objects.get()
        self.assertTrue(msg.image.name.startswith("review_images/"))
        self.assertNotIn("issue", msg.image.name)
        self.assertTrue(response.data["image_url"])
        image_response = self.client.get(urlparse(response.data["image_url"]).path)
        self.assertEqual(image_response.status_code, status.HTTP_200_OK)
        self.assertEqual(image_response["X-Content-Type-Options"], "nosniff")
        self.assertIn("sandbox", image_response["Content-Security-Policy"])

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "apps.reviews.tests.RemoteMemoryStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        }
    )
    def test_review_image_supports_configurable_non_filesystem_storage(self):
        image = SimpleUploadedFile(
            "external.png", _png_bytes(), content_type="image/png",
        )

        response = self.client.post(self.url, {"image": image}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        message = ReviewMessage.objects.get()
        self.assertEqual(storages["default"].__class__.__name__, "RemoteMemoryStorage")
        self.assertTrue(storages["default"].exists(message.image.name))
        self.assertEqual(
            response.data["image_url"],
            f"https://media.invalid/{message.image.name}",
        )

    def test_image_rejects_unsupported_mime_extension_and_oversized_file(self):
        cases = (
            SimpleUploadedFile("issue.png", _png_bytes(), content_type="text/html"),
            SimpleUploadedFile("issue.png.php", _png_bytes(), content_type="image/png"),
            SimpleUploadedFile(
                "issue.png",
                _png_bytes() + b"x" * (5 * 1024 * 1024),
                content_type="image/png",
            ),
        )
        for image in cases:
            with self.subTest(name=image.name, content_type=image.content_type):
                response = self.client.post(self.url, {"image": image}, format="multipart")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_image_rejects_excessive_dimensions_and_truncated_content(self):
        cases = (
            SimpleUploadedFile(
                "wide.png", _image_bytes(size=(4097, 1)), content_type="image/png",
            ),
            SimpleUploadedFile("broken.png", b"\x89PNG\r\n\x1a\n", content_type="image/png"),
        )
        for image in cases:
            with self.subTest(name=image.name):
                response = self.client.post(self.url, {"image": image}, format="multipart")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_image_is_reencoded_without_original_metadata_or_trailing_content(self):
        exif = Image.Exif()
        exif[0x010E] = "不應保留的描述"
        original = _image_bytes(image_format="JPEG", exif=exif) + b"TRAILING-PAYLOAD"
        image = SimpleUploadedFile("same-name.jpg", original, content_type="image/jpeg")

        response = self.client.post(self.url, {"image": image}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        message = ReviewMessage.objects.get()
        with message.image.open("rb") as stored:
            stored_bytes = stored.read()
            stored.seek(0)
            with Image.open(stored) as decoded:
                self.assertEqual(dict(decoded.getexif()), {})
        self.assertNotIn(b"TRAILING-PAYLOAD", stored_bytes)
        self.assertRegex(message.image.name, r"^review_images/[0-9a-f]{32}\.jpg$")

    def test_staff_author_marked_is_admin(self):
        admin = _make_user("admin1", is_staff=True)
        self.client.force_authenticate(admin)
        response = self.client.post(
            self.url, {"body": "官方回覆"}, format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["is_admin"])

    def test_messages_appear_in_review_list(self):
        ReviewMessage.objects.create(
            review=self.review, author=self.user, body="補充", is_admin=False,
        )
        response = self.client.get(reverse("reviews-list"))
        self.assertEqual(len(response.data["reviews"][0]["messages"]), 1)


class ReviewHelpfulTests(APITestCase):
    """W3 新增的點讚 / 排序 / 精選 / 驗證購買功能。"""

    def setUp(self):
        self.alice = _make_user("alice")
        self.bob = _make_user("bob")
        self.review = PlatformReview.objects.create(user=self.alice, rating=5, comment="好用")

    def test_toggle_review_helpful_creates_and_removes(self):
        self.client.force_authenticate(self.bob)
        url = reverse("reviews-helpful", args=[self.review.id])
        # 第一次點 → 加 1
        r1 = self.client.post(url)
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        self.assertEqual(r1.data["helpful_count"], 1)
        self.assertTrue(r1.data["my_helpful"])
        # 第二次點同一則 → 取消（toggle 回 0）
        r2 = self.client.post(url)
        self.assertEqual(r2.data["helpful_count"], 0)
        self.assertFalse(r2.data["my_helpful"])

    def test_helpful_appears_in_list(self):
        from apps.reviews.models import ReviewHelpful
        ReviewHelpful.objects.create(review=self.review, user=self.bob)
        self.client.force_authenticate(self.bob)
        response = self.client.get(reverse("reviews-list"))
        first = response.data["reviews"][0]
        self.assertEqual(first["helpful_count"], 1)
        self.assertTrue(first["my_helpful"])

    def test_sort_helpful_pushes_high_helpful_to_top(self):
        # 多建一則少 helpful 的；alice 的有 helpful，應排前
        review2 = PlatformReview.objects.create(user=self.bob, rating=3, comment="一般")
        from apps.reviews.models import ReviewHelpful
        ReviewHelpful.objects.create(review=self.review, user=self.bob)
        response = self.client.get(reverse("reviews-list") + "?sort=helpful")
        rids = [r["id"] for r in response.data["reviews"]]
        self.assertEqual(rids[0], self.review.id)
        self.assertIn(review2.id, rids)

    def test_featured_review_always_first(self):
        review2 = PlatformReview.objects.create(
            user=self.bob, rating=4, comment="OK", is_featured=True,
        )
        response = self.client.get(reverse("reviews-list"))
        self.assertEqual(response.data["reviews"][0]["id"], review2.id)
        self.assertTrue(response.data["reviews"][0]["is_featured"])

    def test_verified_buyer_flag(self):
        from django.utils import timezone

        from apps.billing.models import PricingPlan, PurchaseOrder
        plan = PricingPlan.objects.get(code="starter")
        PurchaseOrder.objects.create(
            user=self.alice, plan=plan,
            price_ntd=plan.price_ntd, coin_amount=plan.coin_amount,
            buyer_name="A", buyer_email="a@x.com",
            status=PurchaseOrder.Status.PAID,
            paid_at=timezone.now(),
        )
        response = self.client.get(reverse("reviews-list"))
        first = [r for r in response.data["reviews"] if r["id"] == self.review.id][0]
        self.assertTrue(first["verified_buyer"])

    def test_message_helpful_toggle(self):
        msg = ReviewMessage.objects.create(
            review=self.review, author=self.alice, body="補充", is_admin=False,
        )
        self.client.force_authenticate(self.bob)
        r = self.client.post(reverse("reviews-message-helpful", args=[msg.id]))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["helpful_count"], 1)


class ReviewMessageAuthorDisplayTests(APITestCase):
    """admin 在 thread 顯示真名（不再統一寫「Argus 官方」），由前端用 is_admin 加 badge 區分。"""

    def test_admin_display_uses_real_name_not_argus_official(self):
        user = _make_user("u")
        admin = _make_user("admin1", is_staff=True, first_name="王", last_name="管理員")
        review = PlatformReview.objects.create(user=user, rating=5)
        ReviewMessage.objects.create(
            review=review, author=admin, body="官方回覆", is_admin=True,
        )
        response = self.client.get(reverse("reviews-list"))
        msg = response.data["reviews"][0]["messages"][0]
        self.assertEqual(msg["author_display"], "王 管理員")
        self.assertTrue(msg["is_admin"])
        # 不應該寫死「Argus 官方」字串
        self.assertNotIn("Argus", msg["author_display"])
