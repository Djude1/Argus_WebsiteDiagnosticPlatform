"""掃描實際扣點（預扣－退款）與效能量測沒跑的原因（2026-10-08 使用者回報）。"""

from __future__ import annotations

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.billing.services import admin_adjust, settle_scan_actual
from apps.scans import tasks
from apps.scans.coverage import SKIPPED, ScanCoverage
from apps.scans.models import ScanJob

User = get_user_model()


class CoinsChargedTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="coins", email="coins@example.com", password="safe-test-password"
        )
        admin_adjust(target_user=self.user, delta=500, admin_actor=None, note="測試補點")
        self.client.force_authenticate(self.user)

    def _create_scan(self):
        # 不勾全部面向，避開首次免費完整掃描：10 頁 × 1 維度 × 2 點＝預扣 20
        response = self.client.post("/api/scans/", {
            "url": "https://example.com/", "authorization_confirmed": True,
            "max_pages": 10, "categories": ["seo"],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return ScanJob.objects.get(id=response.data["id"])

    def test_in_progress_scan_shows_hold_then_actual_after_settlement(self):
        scan = self._create_scan()
        listed = self.client.get("/api/scans/", {"project": scan.project_id}).data["results"]
        self.assertEqual(listed[0]["coins_charged"], 20)

        # 實際只檢查 3 頁：結算退回 14，實際扣 6
        settle_scan_actual(self.user, scan, 3)
        listed = self.client.get("/api/scans/", {"project": scan.project_id}).data["results"]
        self.assertEqual(listed[0]["coins_charged"], 6)
        detail = self.client.get(f"/api/scans/{scan.id}/").data
        self.assertEqual(detail["coins_charged"], 6)

    def test_wallet_lists_hold_and_refund_with_scan_link(self):
        scan = self._create_scan()
        settle_scan_actual(self.user, scan, 3)
        transactions = self.client.get("/api/billing/wallet/").data["recent_transactions"]
        scan_rows = [t for t in transactions if t["scan_job"] == scan.id]
        self.assertEqual(sorted(t["amount"] for t in scan_rows), [-20, 14])


class PagespeedSkippedReasonTests(APITestCase):
    @override_settings(ARGUS_PAGESPEED_ENABLED=False, ARGUS_PAGESPEED_API_KEY="")
    def test_ux_selected_without_platform_key_records_reason(self):
        ctx = SimpleNamespace(
            scan_job=SimpleNamespace(effective_categories=["ux", "seo"]),
            coverage=ScanCoverage(), scan_job_id=0,
        )
        tasks.stage_pagespeed(ctx)
        self.assertEqual(ctx.coverage.status_of("pagespeed"), SKIPPED)

    @override_settings(ARGUS_PAGESPEED_ENABLED=False, ARGUS_PAGESPEED_API_KEY="")
    def test_ux_not_selected_records_nothing(self):
        ctx = SimpleNamespace(
            scan_job=SimpleNamespace(effective_categories=["seo"]),
            coverage=ScanCoverage(), scan_job_id=0,
        )
        tasks.stage_pagespeed(ctx)
        self.assertIsNone(ctx.coverage.status_of("pagespeed"))
