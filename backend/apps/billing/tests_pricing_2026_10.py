"""2026-10-07 定價調整（docs/business-model-plan.md）：首次免費完整掃描、Partial Scan、
深度資安附加費、免費贈點累積上限、訂閱重新配點、深度資安專家派工上限。
"""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import CoinTransaction, CoinWallet, SubscriptionPlan
from apps.billing.services import (
    affordable_site_pages,
    estimate_scan_cost,
    free_trial_available,
    grant_monthly_bonus_if_needed,
    hold_for_scan,
    settle_scan_actual,
)
from apps.scans.models import ALL_CATEGORIES, ScanJob

User = get_user_model()


def _user(name):
    return User.objects.create_user(
        username=name, email=f"{name}@example.com", password="safe-test-password"
    )


def _full_scan_payload(**extra):
    payload = {
        "url": "https://example.com/",
        "authorization_confirmed": True,
        "max_pages": 50,
        "categories": list(ALL_CATEGORIES),
    }
    payload.update(extra)
    return payload


class FreeTrialScanTests(APITestCase):
    """首次 Standard Full Scan（被動＋整站＋五面向）免費。

    使用者回報：新帳號 200 點、整站五維掃描預扣 520 點，新用戶根本啟動不了產品主打的掃描。
    """

    def setUp(self):
        self.user = _user("trial")
        self.client.force_authenticate(self.user)
        self.url = reverse("scan-list")

    def test_new_user_can_start_a_full_scan_for_free(self):
        response = self.client.post(self.url, _full_scan_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        scan = ScanJob.objects.get()
        self.assertTrue(scan.is_trial)
        self.assertTrue(response.data["is_trial"])
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 200)
        hold = scan.coin_transactions.get(kind=CoinTransaction.Kind.SCAN_HOLD)
        self.assertEqual(hold.amount, 0)

    def test_second_full_scan_is_charged(self):
        self.client.post(self.url, _full_scan_payload(), format="json")
        CoinWallet.objects.filter(user=self.user).update(balance=1000)
        response = self.client.post(self.url, _full_scan_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertFalse(response.data["is_trial"])
        self.assertLess(CoinWallet.objects.get(user=self.user).balance, 1000)

    def test_failed_or_cancelled_trial_does_not_use_up_the_free_scan(self):
        self.client.post(self.url, _full_scan_payload(), format="json")
        self.assertFalse(free_trial_available(self.user))
        ScanJob.objects.update(status=ScanJob.Status.FAILED)
        self.assertTrue(free_trial_available(self.user))

    def test_only_standard_full_scans_qualify(self):
        cases = [
            {"max_pages": 1},  # 單頁
            {"categories": ["seo", "aeo"]},  # 沒有全選五面向
        ]
        for extra in cases:
            with self.subTest(extra=extra):
                ScanJob.objects.all().delete()
                CoinWallet.objects.filter(user=self.user).update(balance=1000)
                response = self.client.post(self.url, _full_scan_payload(**extra), format="json")
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
                self.assertFalse(response.data["is_trial"])

    def test_trial_settles_to_zero(self):
        self.client.post(self.url, _full_scan_payload(), format="json")
        scan = ScanJob.objects.get()
        settle_scan_actual(self.user, scan, 50)
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 200)

    def test_two_trials_at_once_only_one_is_free(self):
        """同時送出兩筆時，第二筆在預扣時被改成付費（錢包鎖住後再確認一次）。"""
        CoinWallet.objects.filter(user=self.user).update(balance=1000)
        first = ScanJob.objects.create(
            user=self.user, original_url="https://example.com/", normalized_url="https://example.com/",
            origin="https://example.com", max_pages=50, is_trial=True,
        )
        hold_for_scan(self.user, first)
        second = ScanJob.objects.create(
            user=self.user, original_url="https://example.com/", normalized_url="https://example.com/",
            origin="https://example.com", max_pages=50, is_trial=True,
        )
        hold_for_scan(self.user, second)
        second.refresh_from_db()
        self.assertFalse(second.is_trial)
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 1000 - 500)

    def test_wallet_api_reports_trial_availability(self):
        data = self.client.get(reverse("billing-wallet")).data
        self.assertTrue(data["free_trial_available"])
        self.client.post(self.url, _full_scan_payload(), format="json")
        data = self.client.get(reverse("billing-wallet")).data
        self.assertFalse(data["free_trial_available"])

    @override_settings(ARGUS_FREE_TRIAL_SCAN_ENABLED=False)
    def test_feature_flag_turns_trial_off(self):
        response = self.client.post(self.url, _full_scan_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(ARGUS_FREE_TRIAL_SCAN_ENABLED=False)
class PartialScanTests(APITestCase):
    """餘額不足時回傳付得起的頁數，由使用者確認（不自動縮小範圍）。"""

    def setUp(self):
        self.user = _user("partial")
        self.client.force_authenticate(self.user)

    @override_settings(ARGUS_AGENT_ENABLED=False)
    def test_insufficient_balance_returns_affordable_pages(self):
        response = self.client.post(reverse("scan-list"), _full_scan_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # 200 點、每頁 10 點 → 最多 20 頁
        self.assertEqual(response.data["affordable_pages"], ["20"])
        self.assertFalse(ScanJob.objects.exists())

    @override_settings(ARGUS_AGENT_ENABLED=True, ARGUS_COIN_AGENT_UX=20)
    def test_affordable_pages_accounts_for_agent_fee(self):
        self.assertEqual(
            affordable_site_pages(200, list(ALL_CATEGORIES), deep_agent=False, max_pages=50), 18
        )

    def test_cannot_afford_two_pages_returns_zero(self):
        self.assertEqual(
            affordable_site_pages(15, list(ALL_CATEGORIES), deep_agent=False, max_pages=50), 0
        )

    @override_settings(ARGUS_AGENT_ENABLED=False)
    def test_confirmed_partial_scan_is_accepted(self):
        response = self.client.post(
            reverse("scan-list"), _full_scan_payload(max_pages=20), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 0)


@override_settings(ARGUS_AGENT_ENABLED=True, ARGUS_COIN_AGENT_DEEP=50, ARGUS_COIN_AGENT_UX=20)
class DeepAgentFeeTests(TestCase):
    """深度資安 Agent 附加費：預扣時算進去，只有 agent 真的跑了才收。"""

    def setUp(self):
        self.user = _user("deep")
        CoinWallet.objects.filter(user=self.user).update(balance=2000)

    def _active_scan(self, max_pages=50):
        return ScanJob.objects.create(
            user=self.user, original_url="https://example.com/",
            normalized_url="https://example.com/", origin="https://example.com",
            max_pages=max_pages, scan_mode=ScanJob.ScanMode.ACTIVE,
            active_testing_authorized=True,
        )

    def test_estimate_includes_deep_fee(self):
        base = estimate_scan_cost(50, list(ALL_CATEGORIES))
        self.assertEqual(estimate_scan_cost(50, list(ALL_CATEGORIES), deep_agent=True), base + 50)
        # 單頁不跑 agent，也不收
        self.assertEqual(
            estimate_scan_cost(1, list(ALL_CATEGORIES), deep_agent=True),
            estimate_scan_cost(1, list(ALL_CATEGORIES)),
        )

    def test_hold_includes_deep_fee(self):
        hold_for_scan(self.user, self._active_scan())
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 2000 - 520 - 50)

    def test_fee_refunded_when_agent_did_not_run(self):
        scan = self._active_scan()
        hold_for_scan(self.user, scan)
        settle_scan_actual(self.user, scan, 50, deep_agent_ran=False)
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 2000 - 520)

    def test_fee_kept_when_agent_ran_even_on_one_page_site(self):
        """只爬到 1 頁的網站，agent 照樣花了 token；附加費不能因頁數少就退掉。"""
        scan = self._active_scan()
        hold_for_scan(self.user, scan)
        settle_scan_actual(self.user, scan, 1, deep_agent_ran=True)
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 2000 - 10 - 50)

    def test_passive_scans_never_pay_deep_fee(self):
        scan = ScanJob.objects.create(
            user=self.user, original_url="https://example.com/",
            normalized_url="https://example.com/", origin="https://example.com", max_pages=50,
        )
        hold_for_scan(self.user, scan)
        settle_scan_actual(self.user, scan, 50, deep_agent_ran=True)
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 2000 - 520)


@override_settings(ARGUS_MONTHLY_BONUS_COINS=200, ARGUS_FREE_BONUS_BALANCE_CAP=600)
class FreeBonusCapTests(TestCase):
    """從未付費的帳號，月贈點只補到 600；付費過的不受限。"""

    def setUp(self):
        self.user = _user("cap")
        # 讓本月贈點尚未發放
        CoinWallet.objects.filter(user=self.user).update(last_bonus_year=2000, last_bonus_month=1)

    def _set_balance(self, balance, purchased=0):
        CoinWallet.objects.filter(user=self.user).update(
            balance=balance, total_purchased_ntd=purchased
        )

    def test_free_user_is_topped_up_to_cap(self):
        self._set_balance(500)
        tx = grant_monthly_bonus_if_needed(self.user)
        self.assertEqual(tx.amount, 100)
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 600)

    def test_free_user_at_cap_gets_nothing_but_month_is_marked(self):
        self._set_balance(700)
        self.assertIsNone(grant_monthly_bonus_if_needed(self.user))
        wallet = CoinWallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, 700)
        now = timezone.now()
        self.assertEqual((wallet.last_bonus_year, wallet.last_bonus_month), (now.year, now.month))

    def test_paying_user_is_not_capped(self):
        self._set_balance(900, purchased=450)
        tx = grant_monthly_bonus_if_needed(self.user)
        self.assertEqual(tx.amount, 200)


class SubscriptionPlanCoinsTests(TestCase):
    """訂閱方案以「每月可做幾次完整掃描」配點（billing/0011 data migration）。"""

    def test_built_in_plans_have_new_monthly_coins(self):
        coins = dict(SubscriptionPlan.objects.values_list("code", "monthly_coins"))
        self.assertEqual(coins.get("sub-lite"), 600)
        self.assertEqual(coins.get("sub-pro"), 1800)
        self.assertEqual(coins.get("sub-team"), 4000)


class SpecialistDispatchLimitTests(TestCase):
    """深度資安指揮官的專家派工上限（runner 需要真瀏覽器，鎖 source 與設定）。"""

    def test_runner_enforces_dispatch_limit(self):
        from django.conf import settings

        from apps.agent import runner as runner_module

        self.assertEqual(settings.ARGUS_AGENT_MAX_SPECIALIST_DISPATCH, 6)
        source = Path(runner_module.__file__).read_text(encoding="utf-8")
        self.assertIn("dispatch_limit_reached", source)
        self.assertIn("[:dispatch_limit]", source, "orchestrator 失效時的全派安全網也要受上限約束")
