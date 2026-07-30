import os
import subprocess
import sys
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.reviews.models import (
    PlatformReview,
    ReviewHelpful,
    ReviewReport,
    ReviewResponse,
    ReviewResponseHelpful,
    ReviewRevision,
)
from apps.reviews.serializers import mask_review_email
from apps.scans.models import ScanJob


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


def _complete_scan(user):
    return ScanJob.objects.create(
        user=user,
        original_url="https://example.com",
        normalized_url="https://example.com/",
        origin="https://example.com",
        status=ScanJob.Status.COMPLETED,
        completed_at=timezone.now(),
    )


def _review(user, *, rating=5, title="掃描結果很清楚", comment=None, **extra):
    return PlatformReview.objects.create(
        user=user,
        rating=rating,
        title=title,
        comment=comment or "掃描結果清楚，修正建議也很容易照著執行。",
        experience_at=timezone.now(),
        **extra,
    )


class ReviewEmailMaskTests(SimpleTestCase):
    def test_mask_never_returns_the_complete_email(self):
        cases = {
            "a@example.test": "a***@example.test",
            "ab@example.test": "a***@example.test",
            "abc@example.test": "ab***@example.test",
            "ab***@example.test": "匿名已驗證使用者",
            "": "匿名已驗證使用者",
            "missing-at.example.test": "匿名已驗證使用者",
            "a@b@example.test": "匿名已驗證使用者",
        }

        for email, expected in cases.items():
            with self.subTest(email=email):
                masked = mask_review_email(email)
                self.assertEqual(masked, expected)
                if email:
                    self.assertNotEqual(masked, email)


class PlatformReviewModelTests(APITestCase):
    def test_one_review_per_user(self):
        user = _make_user("alice")
        _review(user)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _review(user, rating=4)


class ReviewLifecycleAPITests(APITestCase):
    def setUp(self):
        self.user = _make_user(
            "reviewer",
            first_name="不應公開",
            last_name="真實姓名",
        )
        self.client.force_authenticate(self.user)
        self.url = reverse("reviews-mine")

    def test_get_mine_returns_eligibility_without_using_404(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["review"])
        self.assertFalse(response.data["eligibility"]["eligible"])

    def test_completed_scan_is_required_to_create_review(self):
        response = self.client.post(
            self.url,
            {"rating": 5, "comment": "這段評論已有足夠長度，但尚未完成任何掃描。"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(PlatformReview.objects.filter(user=self.user).exists())

    def test_create_review_defaults_to_anonymous_and_ignores_display_name(self):
        scan = _complete_scan(self.user)
        response = self.client.post(
            self.url,
            {
                "rating": 5,
                "title": "報告很容易理解",
                "comment": "第一次使用就能看懂問題優先順序，修正建議也相當具體。",
                "display_name": "不應再接受的公開名稱",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user_display"], "匿名已驗證使用者")
        self.assertFalse(response.data["show_partial_email"])
        self.assertNotIn("display_name", response.data)
        self.assertNotContains(response, self.user.email, status_code=status.HTTP_201_CREATED)
        self.assertNotContains(
            response,
            self.user.first_name,
            status_code=status.HTTP_201_CREATED,
        )
        review = PlatformReview.objects.get(user=self.user)
        self.assertEqual(review.display_name, "")
        self.assertEqual(review.experience_at, scan.completed_at)

    def test_user_can_opt_in_to_masked_email(self):
        _complete_scan(self.user)
        response = self.client.post(
            self.url,
            {
                "rating": 4,
                "comment": "掃描報告的分類完整，讓我能依照風險逐項安排修正。",
                "show_partial_email": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user_display"], "re***@example.com")
        self.assertTrue(response.data["show_partial_email"])
        self.assertNotContains(response, self.user.email, status_code=status.HTTP_201_CREATED)

    def test_owner_can_update_privacy_choice_with_revision(self):
        review = _review(
            self.user,
            rating=3,
            display_name="舊版名稱",
            show_partial_email=False,
        )
        response = self.client.patch(
            self.url,
            {
                "rating": 5,
                "title": "更新後的標題",
                "comment": "重新使用新版功能後體驗改善很多，報告也比以前更容易操作。",
                "display_name": "不應覆寫的名稱",
                "show_partial_email": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user_display"], "re***@example.com")
        review.refresh_from_db()
        self.assertEqual(review.rating, 5)
        self.assertTrue(review.show_partial_email)
        self.assertEqual(review.display_name, "舊版名稱")
        revision = ReviewRevision.objects.get(review=review)
        self.assertEqual(revision.rating, 3)
        self.assertFalse(revision.show_partial_email)
        self.assertEqual(revision.display_name, "舊版名稱")

    def test_owner_can_delete_review(self):
        _review(self.user)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(PlatformReview.objects.filter(user=self.user).exists())

    def test_staff_cannot_create_user_review(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        _complete_scan(self.user)
        response = self.client.post(
            self.url,
            {"rating": 5, "comment": "管理員不應該以一般使用者身分發表平台評論。"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_comment_requires_meaningful_length(self):
        _complete_scan(self.user)
        response = self.client.post(
            self.url,
            {"rating": 5, "comment": "太短"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PublicReviewListTests(APITestCase):
    def setUp(self):
        self.first = _review(_make_user("first"), rating=5)
        self.second = _review(_make_user("second"), rating=4)

    def test_list_is_public_and_hides_non_public_reviews(self):
        self.second.status = PlatformReview.Status.HIDDEN
        self.second.save(update_fields=["status"])
        response = self.client.get(reverse("reviews-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["reviews"][0]["id"], self.first.id)

    def test_public_identity_uses_only_anonymous_or_masked_email(self):
        self.first.display_name = "舊版公開名稱"
        self.first.save(update_fields=["display_name"])
        self.second.show_partial_email = True
        self.second.save(update_fields=["show_partial_email"])

        response = self.client.get(reverse("reviews-list"))
        displays = {
            review["id"]: review["user_display"]
            for review in response.data["reviews"]
        }

        self.assertEqual(displays[self.first.id], "匿名已驗證使用者")
        self.assertEqual(displays[self.second.id], "se***@example.com")
        self.assertNotContains(response, self.first.user.email)
        self.assertNotContains(response, self.second.user.email)

    def test_unverified_legacy_review_is_not_public_or_counted(self):
        self.second.experience_at = None
        self.second.save(update_fields=["experience_at"])

        reviews = self.client.get(reverse("reviews-list"))
        summary = self.client.get(reverse("reviews-summary"))

        self.assertEqual(reviews.data["total"], 1)
        self.assertEqual(reviews.data["reviews"][0]["id"], self.first.id)
        self.assertEqual(summary.data["total"], 1)
        self.assertEqual(summary.data["average"], 5.0)

    def test_rating_distribution_summary_and_filter(self):
        summary = self.client.get(reverse("reviews-summary"))
        self.assertEqual(summary.data["total"], 2)
        self.assertEqual(summary.data["average"], 4.5)
        self.assertEqual(summary.data["distribution"]["5"], 1)

        filtered = self.client.get(reverse("reviews-list"), {"rating": 4})
        self.assertEqual(filtered.data["total"], 1)
        self.assertEqual(filtered.data["reviews"][0]["rating"], 4)

    def test_helpful_sort_uses_real_votes_without_featured_override(self):
        self.first.is_featured = True
        self.first.save(update_fields=["is_featured"])
        voters = [_make_user(f"voter-{index}") for index in range(2)]
        ReviewHelpful.objects.bulk_create([
            ReviewHelpful(review=self.second, user=voter) for voter in voters
        ])
        response = self.client.get(reverse("reviews-list"), {"sort": "helpful"})
        self.assertEqual(response.data["reviews"][0]["id"], self.second.id)

    def test_list_is_paginated(self):
        for index in range(7):
            _review(_make_user(f"extra-{index}"))
        response = self.client.get(reverse("reviews-list"))
        self.assertEqual(response.data["total"], 9)
        self.assertEqual(response.data["total_pages"], 2)
        self.assertEqual(len(response.data["reviews"]), 8)


class ReviewTrustActionsTests(APITestCase):
    def setUp(self):
        self.owner = _make_user("owner")
        self.reader = _make_user("reader")
        self.review = _review(self.owner)

    def test_owner_cannot_mark_own_review_helpful(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            reverse("reviews-helpful", kwargs={"review_id": self.review.id}),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_helpful_vote_toggles_for_another_user(self):
        self.client.force_authenticate(self.reader)
        url = reverse("reviews-helpful", kwargs={"review_id": self.review.id})
        first = self.client.post(url)
        second = self.client.post(url)
        self.assertTrue(first.data["my_helpful"])
        self.assertFalse(second.data["my_helpful"])

    def test_official_response_has_its_own_helpful_state(self):
        admin = _make_user("response-author", is_staff=True)
        official_response = ReviewResponse.objects.create(
            review=self.review,
            author=admin,
            body="這是針對使用者回饋提供的官方處理說明。",
        )
        self.client.force_authenticate(self.reader)
        url = reverse(
            "reviews-response-helpful",
            kwargs={"response_id": official_response.id},
        )

        created = self.client.post(url)
        listing = self.client.get(reverse("reviews-list"))
        removed = self.client.post(url)

        self.assertEqual(created.status_code, status.HTTP_200_OK)
        self.assertTrue(created.data["my_helpful"])
        self.assertEqual(created.data["helpful_count"], 1)
        self.assertEqual(listing.data["reviews"][0]["response"]["id"], official_response.id)
        self.assertEqual(listing.data["reviews"][0]["response"]["helpful_count"], 1)
        self.assertTrue(listing.data["reviews"][0]["response"]["my_helpful"])
        self.assertFalse(removed.data["my_helpful"])
        self.assertFalse(ReviewResponseHelpful.objects.exists())

    def test_official_response_author_cannot_like_own_response(self):
        admin = _make_user("response-owner", is_staff=True)
        official_response = ReviewResponse.objects.create(
            review=self.review,
            author=admin,
            body="官方回覆內容",
        )
        self.client.force_authenticate(admin)

        response = self.client.post(reverse(
            "reviews-response-helpful",
            kwargs={"response_id": official_response.id},
        ))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_report_is_unique_and_owner_cannot_report_self(self):
        url = reverse("reviews-report", kwargs={"review_id": self.review.id})
        self.client.force_authenticate(self.owner)
        own = self.client.post(url, {"reason": ReviewReport.Reason.OTHER}, format="json")
        self.assertEqual(own.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(self.reader)
        created = self.client.post(
            url,
            {"reason": ReviewReport.Reason.PRIVACY, "detail": "疑似含有個人資料"},
            format="json",
        )
        duplicate = self.client.post(
            url,
            {"reason": ReviewReport.Reason.SPAM},
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ReviewReport.objects.filter(review=self.review).count(), 1)

    def test_review_and_official_response_can_be_reported_separately(self):
        admin = _make_user("reported-response-author", is_staff=True)
        official_response = ReviewResponse.objects.create(
            review=self.review,
            author=admin,
            body="需要被獨立檢視的官方回覆內容",
        )
        self.client.force_authenticate(self.reader)

        review_report = self.client.post(
            reverse("reviews-report", kwargs={"review_id": self.review.id}),
            {"reason": ReviewReport.Reason.OTHER},
            format="json",
        )
        response_report = self.client.post(
            reverse(
                "reviews-response-report",
                kwargs={"response_id": official_response.id},
            ),
            {"reason": ReviewReport.Reason.ABUSE},
            format="json",
        )
        duplicate = self.client.post(
            reverse(
                "reviews-response-report",
                kwargs={"response_id": official_response.id},
            ),
            {"reason": ReviewReport.Reason.SPAM},
            format="json",
        )

        self.assertEqual(review_report.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response_report.status_code, status.HTTP_201_CREATED)
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            ReviewReport.objects.filter(review=self.review, response__isnull=True).count(),
            1,
        )
        self.assertEqual(
            ReviewReport.objects.filter(review=self.review, response=official_response).count(),
            1,
        )

    def test_unverified_review_and_response_cannot_be_interacted_with(self):
        official_response = ReviewResponse.objects.create(
            review=self.review,
            author=_make_user("legacy-response-author", is_staff=True),
            body="Legacy response",
        )
        self.review.experience_at = None
        self.review.save(update_fields=["experience_at"])
        self.client.force_authenticate(self.reader)

        requests = [
            self.client.post(reverse("reviews-helpful", args=[self.review.id])),
            self.client.post(
                reverse("reviews-report", args=[self.review.id]),
                {"reason": ReviewReport.Reason.OTHER},
                format="json",
            ),
            self.client.post(reverse("reviews-response-helpful", args=[official_response.id])),
            self.client.post(
                reverse("reviews-response-report", args=[official_response.id]),
                {"reason": ReviewReport.Reason.OTHER},
                format="json",
            ),
        ]

        self.assertTrue(all(
            response.status_code == status.HTTP_404_NOT_FOUND
            for response in requests
        ))

    def test_official_response_author_cannot_report_own_response(self):
        admin = _make_user("self-reporting-response-author", is_staff=True)
        official_response = ReviewResponse.objects.create(
            review=self.review,
            author=admin,
            body="Official response",
        )
        self.client.force_authenticate(admin)

        response = self.client.post(
            reverse("reviews-response-report", args=[official_response.id]),
            {"reason": ReviewReport.Reason.OTHER},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_legacy_public_message_routes_are_removed(self):
        self.client.force_authenticate(self.reader)
        response = self.client.post(f"/api/reviews/{self.review.id}/messages/", {})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
