"""掃描終止（cancel）功能測試。

涵蓋：
- API：擁有者進行中可 cancel 200；非進行中 400；跨使用者 404
- helper：is_cancelled 對應 status；raise_if_cancelled 行為
- exception：ScanCancelled 可被 catch
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from apps.scans.cancellation import (
    ScanCancelled,
    is_cancelled,
    raise_if_cancelled,
)
from apps.scans.models import ScanJob


def _make_scan(user, status_value=ScanJob.Status.CRAWLING) -> ScanJob:
    return ScanJob.objects.create(
        user=user,
        original_url="https://example.com/",
        normalized_url="https://example.com/",
        origin="https://example.com",
        status=status_value,
    )


class ScanCancelApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="cancel_user", password="safe-test-password"
        )
        self.client.force_authenticate(self.user)

    def _url(self, scan_id):
        return reverse("scan-cancel", kwargs={"pk": scan_id})

    def test_cancel_in_progress_scan_succeeds(self):
        scan = _make_scan(self.user, ScanJob.Status.CRAWLING)
        resp = self.client.post(self._url(scan.id))
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.json()["status"], ScanJob.Status.CANCELLED)
        scan.refresh_from_db()
        self.assertEqual(scan.status, ScanJob.Status.CANCELLED)

    def test_cancel_queued_scan_succeeds(self):
        scan = _make_scan(self.user, ScanJob.Status.QUEUED)
        resp = self.client.post(self._url(scan.id))
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

    def test_cancel_scanning_scan_succeeds(self):
        scan = _make_scan(self.user, ScanJob.Status.SCANNING)
        resp = self.client.post(self._url(scan.id))
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

    def test_cannot_cancel_completed_scan(self):
        scan = _make_scan(self.user, ScanJob.Status.COMPLETED)
        resp = self.client.post(self._url(scan.id))
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertIn("無法終止", resp.json()["detail"])
        scan.refresh_from_db()
        self.assertEqual(scan.status, ScanJob.Status.COMPLETED)

    def test_cannot_cancel_failed_scan(self):
        scan = _make_scan(self.user, ScanJob.Status.FAILED)
        resp = self.client.post(self._url(scan.id))
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_cannot_cancel_already_cancelled_scan(self):
        scan = _make_scan(self.user, ScanJob.Status.CANCELLED)
        resp = self.client.post(self._url(scan.id))
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_other_user_cannot_cancel(self):
        scan = _make_scan(self.user, ScanJob.Status.CRAWLING)
        other = get_user_model().objects.create_user(
            username="cancel_other", password="safe-test-password"
        )
        self.client.force_authenticate(other)
        resp = self.client.post(self._url(scan.id))
        self.assertEqual(resp.status_code, http_status.HTTP_404_NOT_FOUND)
        scan.refresh_from_db()
        self.assertEqual(scan.status, ScanJob.Status.CRAWLING)

    def test_unauthenticated_cannot_cancel(self):
        scan = _make_scan(self.user, ScanJob.Status.CRAWLING)
        self.client.logout()
        resp = self.client.post(self._url(scan.id))
        self.assertEqual(resp.status_code, http_status.HTTP_401_UNAUTHORIZED)


class CancellationHelperTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="helper_cancel", password="safe-test-password"
        )

    def test_is_cancelled_returns_true_for_cancelled_status(self):
        scan = _make_scan(self.user, ScanJob.Status.CANCELLED)
        self.assertTrue(is_cancelled(scan.id))

    def test_is_cancelled_returns_false_for_other_statuses(self):
        for s in [
            ScanJob.Status.QUEUED,
            ScanJob.Status.CRAWLING,
            ScanJob.Status.SCANNING,
            ScanJob.Status.COMPLETED,
            ScanJob.Status.FAILED,
        ]:
            scan = _make_scan(self.user, s)
            self.assertFalse(is_cancelled(scan.id))

    def test_is_cancelled_returns_false_for_missing_scan(self):
        self.assertFalse(is_cancelled(999_999))

    def test_raise_if_cancelled_raises_when_cancelled(self):
        scan = _make_scan(self.user, ScanJob.Status.CANCELLED)
        with self.assertRaises(ScanCancelled):
            raise_if_cancelled(scan.id)

    def test_raise_if_cancelled_silent_when_not_cancelled(self):
        scan = _make_scan(self.user, ScanJob.Status.CRAWLING)
        # 不該 raise
        raise_if_cancelled(scan.id)
