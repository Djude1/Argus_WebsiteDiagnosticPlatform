from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from apps.reviews.models import PlatformReview, ReviewMessage


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
        self.assertTrue(response.data["image_url"])

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
