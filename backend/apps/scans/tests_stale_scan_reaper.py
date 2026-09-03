"""卡住的掃描回收（worker 被砍時的收斂機制）。

事故背景：worker pod 被 rollout / OOM / 節點驅逐砍掉時，Celery 的
`acks_late` 預設為 False——訊息在派送時就已 ACK，不會重新投遞。而 run_scan_job
只防得住 ScanCancelled / SoftTimeLimitExceeded / 一般例外這三種「Python 層還跑得到
handler」的死法。被 SIGKILL 時沒有任何 handler 會執行，於是：

  ScanJob 永遠停在 crawling / scanning，hold_for_scan 扣的 coin 永遠不退。

使用者實際遇過一次（卡 95 分鐘），而每次部署都會重新觸發。
run_scan_job 的入口 CAS 是 filter(status=QUEUED)，所以就算訊息被重投也只會
直接 return，不會真的重跑——光靠 acks_late 修不了，必須有回收機制。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.billing.models import CoinTransaction, CoinWallet
from apps.billing.services import hold_for_scan
from apps.scans.models import ScanJob
from apps.scans.tasks import reap_stale_scans

User = get_user_model()


class ReapStaleScansTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="reap", password="safe-test-password")
        CoinWallet.objects.filter(user=self.user).update(balance=1000)

    def _scan(self, *, status, started_minutes_ago: int | None, max_pages: int = 10) -> ScanJob:
        scan_job = ScanJob.objects.create(
            user=self.user, original_url="https://example.com/",
            normalized_url="https://example.com/", origin="example.com",
            status=status, max_pages=max_pages,
            started_at=(
                timezone.now() - timezone.timedelta(minutes=started_minutes_ago)
                if started_minutes_ago is not None else None
            ),
        )
        hold_for_scan(self.user, scan_job)
        return scan_job

    def _balance(self) -> int:
        return CoinWallet.objects.get(user=self.user).balance

    def test_scan_stuck_past_the_hard_time_limit_is_failed_and_refunded(self):
        """超過硬性上限還在非終態＝worker 已經不在了，Python 層不會有 handler 跑。"""
        scan_job = self._scan(status=ScanJob.Status.SCANNING, started_minutes_ago=120)
        held = self._balance()

        reaped = reap_stale_scans()

        scan_job.refresh_from_db()
        self.assertEqual(reaped, 1)
        self.assertEqual(scan_job.status, ScanJob.Status.FAILED)
        self.assertGreater(self._balance(), held)

    def test_scan_still_within_the_time_limit_is_left_alone(self):
        """還在跑的掃描不能被誤殺。"""
        scan_job = self._scan(status=ScanJob.Status.CRAWLING, started_minutes_ago=5)

        self.assertEqual(reap_stale_scans(), 0)
        scan_job.refresh_from_db()
        self.assertEqual(scan_job.status, ScanJob.Status.CRAWLING)

    def test_completed_scan_is_never_touched(self):
        scan_job = self._scan(status=ScanJob.Status.COMPLETED, started_minutes_ago=500)

        self.assertEqual(reap_stale_scans(), 0)
        scan_job.refresh_from_db()
        self.assertEqual(scan_job.status, ScanJob.Status.COMPLETED)

    def test_queued_scan_that_never_started_is_also_reaped(self):
        """enqueue 後 worker 從沒取件：started_at 是 None，用 created_at 判斷。"""
        scan_job = self._scan(status=ScanJob.Status.QUEUED, started_minutes_ago=None)
        ScanJob.objects.filter(id=scan_job.id).update(
            created_at=timezone.now() - timezone.timedelta(minutes=200)
        )

        self.assertEqual(reap_stale_scans(), 1)
        scan_job.refresh_from_db()
        self.assertEqual(scan_job.status, ScanJob.Status.FAILED)

    def test_refund_is_idempotent_across_repeated_runs(self):
        """回收會週期性執行，重跑不能重複退款——退錯錢比不退更糟。"""
        self._scan(status=ScanJob.Status.SCANNING, started_minutes_ago=120)
        reap_stale_scans()
        balance_after_first = self._balance()
        refunds = CoinTransaction.objects.filter(
            kind=CoinTransaction.Kind.SCAN_REFUND
        ).count()

        self.assertEqual(reap_stale_scans(), 0)   # 已是終態，不再處理

        self.assertEqual(self._balance(), balance_after_first)
        self.assertEqual(
            CoinTransaction.objects.filter(kind=CoinTransaction.Kind.SCAN_REFUND).count(),
            refunds,
        )

    def test_error_message_explains_what_happened(self):
        """使用者要看得懂為什麼失敗，不是只看到一個空白的 failed。"""
        scan_job = self._scan(status=ScanJob.Status.SCANNING, started_minutes_ago=120)

        reap_stale_scans()

        scan_job.refresh_from_db()
        self.assertIn("中斷", scan_job.error_message)

    def test_one_broken_scan_does_not_stop_the_rest(self):
        """回收是批次作業：一筆退款失敗不該讓其他卡住的掃描continue卡著。"""
        good = self._scan(status=ScanJob.Status.SCANNING, started_minutes_ago=120)
        other = self._scan(status=ScanJob.Status.CRAWLING, started_minutes_ago=130)

        self.assertEqual(reap_stale_scans(), 2)
        for scan_job in (good, other):
            scan_job.refresh_from_db()
            self.assertEqual(scan_job.status, ScanJob.Status.FAILED)
