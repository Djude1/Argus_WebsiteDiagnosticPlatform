"""掃描的 finding 計數端點（2026-09-03 前端佔比失真回歸測試）。

事故：前端的「各類別 finding 佔比」與嚴重度長條，是用 `/findings/?scan_id=` 抓回來
的清單自己數的——但那個端點有分頁（預設 100 筆）。findings 一多就只算到第一頁：

- 掃描中總數 < 100 → 三個分類都看得到
- 掃描完成後總數遠超 100 → 排序靠後的分類（AEO）掉出第一頁 → **從圖上消失**

而且顯示的百分比是「前 100 筆的佔比」而非全體，會讓人誤判問題分佈。
計數必須由 DB 算。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.scans.models import Finding, ScanJob

User = get_user_model()


class FindingStatsEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="stats", password="safe-test-password")
        self.scan_job = ScanJob.objects.create(
            user=self.user, original_url="https://example.com/",
            normalized_url="https://example.com/", origin="example.com",
            status=ScanJob.Status.COMPLETED, completed_at=timezone.now(),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _finding(self, category: str, severity: str, priority: float, index: int):
        Finding.objects.create(
            scan_job=self.scan_job, page=None, category=category, severity=severity,
            title=f"{category}-{index}", description="d", remediation="r",
            rule_id=f"{category}-{index}", ai_handoff_prompt="p", priority_score=priority,
        )

    def _stats(self) -> dict:
        response = self.client.get(f"/api/scans/{self.scan_job.id}/finding-stats/")
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_counts_are_complete_beyond_the_first_page(self):
        """這就是事故本身：150 筆時，只看第一頁會少算 50 筆。"""
        for index in range(150):
            self._finding("seo", "low", 40.0, index)

        self.assertEqual(self._stats()["by_category"]["seo"], 150)

    def test_low_priority_category_is_not_lost_behind_high_priority_ones(self):
        """AEO 消失的直接重現：SEO 佔滿第一頁，AEO 排在後面。"""
        for index in range(120):
            self._finding("seo", "medium", 90.0, index)
        for index in range(3):
            self._finding("aeo", "info", 5.0, index)

        stats = self._stats()

        self.assertEqual(stats["by_category"]["aeo"], 3)
        self.assertEqual(stats["by_category"]["seo"], 120)
        self.assertEqual(stats["total"], 123)

    def test_severity_counts_are_also_complete(self):
        for index in range(120):
            self._finding("seo", "low", 40.0, index)
        for index in range(5):
            self._finding("security", "critical", 95.0, index)

        stats = self._stats()

        self.assertEqual(stats["by_severity"]["critical"], 5)
        self.assertEqual(stats["by_severity"]["low"], 120)

    def test_empty_scan_returns_zero_totals(self):
        stats = self._stats()

        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["by_category"], {})
        self.assertEqual(stats["by_severity"], {})

    def test_other_users_cannot_read_the_stats(self):
        other = User.objects.create_user(username="other", password="safe-test-password")
        client = APIClient()
        client.force_authenticate(user=other)

        response = client.get(f"/api/scans/{self.scan_job.id}/finding-stats/")

        self.assertEqual(response.status_code, 404)

    def test_anonymous_is_rejected(self):
        response = APIClient().get(f"/api/scans/{self.scan_job.id}/finding-stats/")

        self.assertIn(response.status_code, (401, 403))
