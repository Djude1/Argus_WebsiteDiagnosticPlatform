"""修正產出 API：觸發／狀態／產物（spec docs/specs/0002-fix-output.md 票04）。

以 Django test client 驗證：
- 觸發：額度→點數計費閘門（先扣後派）、冪等不重複扣款、僅限完成掃描、
  功能關閉 503、餘額不足 400 且不派工
- 狀態：輪詢回 idle/generating/ready/failed（含原因）
- 產物：ready 才可讀取；llms.txt 以檔案下載交付；僅掃描擁有者可存取
- 產生失敗全額退點（服務層 _fail 收斂路徑）
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import CoinTransaction, CoinWallet
from apps.billing.services import (
    admin_adjust,
    grant_fixgen_entitlement,
    hold_for_scan,
    settle_scan_actual,
)
from apps.scans.fixgen.services import run_fix_output, trigger_fix_output
from apps.scans.models import FixOutput, Page, ScanJob
from apps.scans.tests_fixgen import _fake_chain

User = get_user_model()

READY_ARTIFACTS = {
    "json_ld": {"content": "<script>...</script>", "fields": {"name": {"status": "verified"}}},
    "og_meta": {"content": '<meta property="og:title" content="t">', "fields": {}},
    "llms_txt": {"content": "# 站名\n> 摘要", "fields": {}},
}


def _make_completed_scan(user) -> ScanJob:
    scan = ScanJob.objects.create(
        user=user,
        original_url="https://api.example.com/",
        normalized_url="https://api.example.com/",
        origin="https://api.example.com",
        status=ScanJob.Status.COMPLETED,
    )
    Page.objects.create(
        scan_job=scan,
        url="https://api.example.com/",
        final_url="https://api.example.com/",
        origin="https://api.example.com",
        status_code=200,
        title="API 測試首頁",
        html="<html><head><title>API 測試首頁</title></head><body><h1>主題</h1></body></html>",
        depth=0,
    )
    return scan


def _paid_scan(user, admin) -> ScanJob:
    """走過 hold → settle 的付費掃描，並附贈產生額度。"""
    admin_adjust(target_user=user, delta=300, admin_actor=admin, note="test")
    scan = _make_completed_scan(user)
    hold_for_scan(user, scan)
    settle_scan_actual(user, scan, 5)
    grant_fixgen_entitlement(user, scan)
    return scan


class FixOutputTriggerAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="fixgen-api-user",
            email="fixgen-api@example.com",
            password="safe-test-password",
        )
        self.admin = User.objects.create_user(
            username="fixgen-api-admin",
            email="fixgen-api-admin@example.com",
            password="safe-test-password",
            is_superuser=True,
        )
        self.client.force_authenticate(user=self.user)

    def _url(self, scan, suffix=""):
        return f"/api/scans/{scan.id}/fix-output/{suffix}".rstrip("/") + "/"

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_trigger_consumes_entitlement_and_dispatches(self):
        scan = _paid_scan(self.user, self.admin)

        with patch("apps.scans.fixgen.services.run_fix_output_task") as task:
            response = self.client.post(self._url(scan, "trigger"))

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue(response.data["dispatched"])
        self.assertEqual(response.data["fix_output"]["status"], "generating")
        task.delay.assert_called_once_with(scan.id)
        # 計費走額度（0 元），餘額不動
        self.assertTrue(
            CoinTransaction.objects.filter(
                scan_job=scan,
                kind=CoinTransaction.Kind.FIXGEN_CHARGE,
                amount=0,
            ).exists()
        )

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_trigger_without_entitlement_charges_coins(self):
        scan = _make_completed_scan(self.user)  # 無額度
        admin_adjust(target_user=self.user, delta=100, admin_actor=self.admin, note="test")
        balance_before = CoinWallet.objects.get(user=self.user).balance

        with patch("apps.scans.fixgen.services.run_fix_output_task"):
            response = self.client.post(self._url(scan, "trigger"))

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(
            CoinWallet.objects.get(user=self.user).balance, balance_before - 30
        )

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_trigger_insufficient_coins_rejects_without_dispatch(self):
        scan = _make_completed_scan(self.user)  # 無額度
        CoinWallet.objects.filter(user=self.user).update(balance=5)

        with patch("apps.scans.fixgen.services.run_fix_output_task") as task:
            response = self.client.post(self._url(scan, "trigger"))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("required", response.data)
        task.delay.assert_not_called()
        self.assertEqual(FixOutput.objects.get(scan_job=scan).status, FixOutput.Status.IDLE)

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_trigger_ready_output_is_idempotent_no_recharge(self):
        scan = _paid_scan(self.user, self.admin)
        FixOutput.objects.update_or_create(
            scan_job=scan,
            defaults={"status": FixOutput.Status.READY, "artifacts": READY_ARTIFACTS},
        )

        with patch("apps.scans.fixgen.services.run_fix_output_task") as task:
            response = self.client.post(self._url(scan, "trigger"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["dispatched"])
        self.assertEqual(response.data["fix_output"]["status"], "ready")
        task.delay.assert_not_called()
        self.assertFalse(
            CoinTransaction.objects.filter(
                scan_job=scan, kind=CoinTransaction.Kind.FIXGEN_CHARGE
            ).exists()
        )

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_trigger_requires_completed_scan(self):
        scan = _make_completed_scan(self.user)
        ScanJob.objects.filter(pk=scan.pk).update(status=ScanJob.Status.SCANNING)

        response = self.client.post(self._url(scan, "trigger"))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_trigger_disabled_returns_503(self):
        scan = _make_completed_scan(self.user)

        response = self.client.post(self._url(scan, "trigger"))

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_trigger_only_owner_can_access(self):
        scan = _paid_scan(self.user, self.admin)
        other = User.objects.create_user(
            username="fixgen-other", email="other@example.com", password="safe-test-password"
        )
        self.client.force_authenticate(user=other)

        response = self.client.post(self._url(scan, "trigger"))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class FixOutputStatusAndArtifactsAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="fixgen-art-user",
            email="fixgen-art@example.com",
            password="safe-test-password",
        )
        self.scan = _make_completed_scan(self.user)
        self.client.force_authenticate(user=self.user)

    def _url(self, scan, suffix=""):
        return f"/api/scans/{scan.id}/fix-output/{suffix}".rstrip("/") + "/"

    def test_status_idle_when_never_triggered(self):
        response = self.client.get(self._url(self.scan, "status"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "idle")

    def test_status_ready_lists_artifact_keys(self):
        FixOutput.objects.update_or_create(
            scan_job=self.scan,
            defaults={"status": FixOutput.Status.READY, "artifacts": READY_ARTIFACTS},
        )

        response = self.client.get(self._url(self.scan, "status"))

        self.assertEqual(response.data["status"], "ready")
        self.assertEqual(
            set(response.data["artifact_keys"]), {"json_ld", "og_meta", "llms_txt"}
        )

    def test_status_failed_includes_reason(self):
        FixOutput.objects.update_or_create(
            scan_job=self.scan,
            defaults={"status": FixOutput.Status.FAILED, "error": "LLM 回應不是有效的 JSON"},
        )

        response = self.client.get(self._url(self.scan, "status"))

        self.assertEqual(response.data["status"], "failed")
        self.assertIn("JSON", response.data["error"])

    def test_artifacts_require_ready(self):
        FixOutput.objects.update_or_create(
            scan_job=self.scan, defaults={"status": FixOutput.Status.GENERATING}
        )

        response = self.client.get(self._url(self.scan, "artifacts"))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_artifacts_returns_full_payload(self):
        FixOutput.objects.update_or_create(
            scan_job=self.scan,
            defaults={"status": FixOutput.Status.READY, "artifacts": READY_ARTIFACTS},
        )

        response = self.client.get(self._url(self.scan, "artifacts"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["artifacts"]["json_ld"]["content"], "<script>...</script>")
        self.assertEqual(
            response.data["artifacts"]["json_ld"]["fields"]["name"]["status"], "verified"
        )

    def test_llms_txt_downloads_as_attachment(self):
        FixOutput.objects.update_or_create(
            scan_job=self.scan,
            defaults={"status": FixOutput.Status.READY, "artifacts": READY_ARTIFACTS},
        )

        response = self.client.get(self._url(self.scan, "artifacts"), {"download": "llms_txt"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("llms.txt", response["Content-Disposition"])
        self.assertIn("text/markdown", response["Content-Type"])
        self.assertIn("# 站名", response.content.decode("utf-8"))

    def test_download_rejects_non_file_artifacts(self):
        FixOutput.objects.update_or_create(
            scan_job=self.scan,
            defaults={"status": FixOutput.Status.READY, "artifacts": READY_ARTIFACTS},
        )

        response = self.client.get(self._url(self.scan, "artifacts"), {"download": "json_ld"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class FixOutputFailureRefundTests(APITestCase):
    """產生失敗全額退點——服務層 _fail 收斂路徑。"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="fixgen-refund-user",
            email="fixgen-refund@example.com",
            password="safe-test-password",
        )
        self.admin = User.objects.create_user(
            username="fixgen-refund-admin",
            email="fixgen-refund-admin@example.com",
            password="safe-test-password",
            is_superuser=True,
        )

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_failed_generation_refunds_coins(self):
        from apps.agent.providers import ProviderError

        scan = _make_completed_scan(self.user)
        admin_adjust(target_user=self.user, delta=100, admin_actor=self.admin, note="test")
        balance_before = CoinWallet.objects.get(user=self.user).balance

        with patch("apps.scans.fixgen.services.run_fix_output_task"):
            fix_output, dispatched = trigger_fix_output(scan)
        self.assertTrue(dispatched)
        balance_charged = CoinWallet.objects.get(user=self.user).balance
        self.assertEqual(balance_charged, balance_before - 30)

        run_fix_output(
            scan.id, chain=_fake_chain(error=ProviderError("fake", 500, "non-200"))
        )

        fix_output.refresh_from_db()
        self.assertEqual(fix_output.status, FixOutput.Status.FAILED)
        self.assertNotEqual(fix_output.error, "")
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, balance_before)

    @override_settings(ARGUS_FIXGEN_ENABLED=True)
    def test_failed_generation_returns_entitlement(self):
        scan = _paid_scan(self.user, self.admin)

        with patch("apps.scans.fixgen.services.run_fix_output_task"):
            _, dispatched = trigger_fix_output(scan)
        self.assertTrue(dispatched)

        run_fix_output(scan.id, chain=_fake_chain(payload={"not": "the contract"}))

        # 額度已返還：重新觸發又是 0 元
        with patch("apps.scans.fixgen.services.run_fix_output_task"):
            _, dispatched = trigger_fix_output(scan)
            self.assertTrue(dispatched)
        self.assertTrue(
            CoinTransaction.objects.filter(
                scan_job=scan, kind=CoinTransaction.Kind.FIXGEN_REFUND, amount=0
            ).exists()
        )
