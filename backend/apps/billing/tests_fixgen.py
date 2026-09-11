"""修正產出的額度與計費（billing services 擴充，spec docs/specs/0002-fix-output.md）。

模型：產生額度以交易紀錄表達——
- FIXGEN_GRANT（amount=0）：付費掃描結算時附贈 1 次額度，同掃描只贈一次
- FIXGEN_CHARGE：觸發產生前計費；額度內 amount=0（消耗額度）、額度外扣固定點數
- FIXGEN_REFUND：產生失敗退費；點數退點（正數）、額度返還（amount=0）

額度可用判定＝有贈與，且 0 元扣款未被 0 元退款抵銷——重試失敗後額度會回來。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.billing.models import CoinTransaction, CoinWallet
from apps.billing.services import (
    InsufficientCoinError,
    admin_adjust,
    charge_fixgen_generation,
    fixgen_entitlement_available,
    get_or_create_wallet,
    grant_fixgen_entitlement,
    hold_for_scan,
    is_paid_tier,
    refund_fixgen_generation,
    settle_scan_actual,
)
from apps.scans.models import ScanJob

User = get_user_model()


def _make_scan(user, *, max_pages=10) -> ScanJob:
    return ScanJob.objects.create(
        user=user,
        original_url="https://billing.example.com/",
        normalized_url="https://billing.example.com/",
        origin="https://billing.example.com",
        status=ScanJob.Status.COMPLETED,
        max_pages=max_pages,
    )


class FixgenBillingTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="fixgen-billing",
            email="fixgen-billing@example.com",
            password="safe-test-password",
        )
        self.admin = User.objects.create_user(
            username="fixgen-admin",
            email="fixgen-admin@example.com",
            password="safe-test-password",
            is_superuser=True,
        )
        self.wallet = get_or_create_wallet(self.user)

    def _top_up(self, coins: int) -> None:
        admin_adjust(target_user=self.user, delta=coins, admin_actor=self.admin, note="test")

    def _balance(self) -> int:
        """每次都從 DB 重讀——user 建立時的月贈點 signal 會讓快取失真。"""
        return CoinWallet.objects.get(user=self.user).balance

    def _paid_scan(self, *, actual_pages: int = 5, max_pages: int = 10) -> ScanJob:
        """建立一個真實走過 hold → settle 的付費掃描（實扣 50 coin）。"""
        self._top_up(200)
        scan = _make_scan(self.user, max_pages=max_pages)
        hold_for_scan(self.user, scan)
        settle_scan_actual(self.user, scan, actual_pages)
        return scan

    def test_grant_after_paid_scan_is_idempotent_and_free(self):
        scan = self._paid_scan()
        balance_before = self._balance()

        tx = grant_fixgen_entitlement(self.user, scan)
        again = grant_fixgen_entitlement(self.user, scan)

        self.assertIsNotNone(tx)
        self.assertEqual(tx.kind, CoinTransaction.Kind.FIXGEN_GRANT)
        self.assertEqual(tx.amount, 0)
        self.assertIsNone(again)
        self.assertEqual(
            CoinTransaction.objects.filter(
                wallet=self.wallet, kind=CoinTransaction.Kind.FIXGEN_GRANT
            ).count(),
            1,
        )
        self.assertEqual(self._balance(), balance_before)  # 贈額度不動餘額

    def test_no_grant_for_scan_with_no_net_charge(self):
        scan = _make_scan(self.user)  # 沒有 hold/settle → 淨扣 0

        self.assertIsNone(grant_fixgen_entitlement(self.user, scan))

    def test_charge_consumes_entitlement_before_coins(self):
        scan = self._paid_scan()
        grant_fixgen_entitlement(self.user, scan)
        balance_before = self._balance()

        with_entitlement = charge_fixgen_generation(self.user, scan)
        self.assertEqual(with_entitlement.amount, 0)
        self.assertEqual(with_entitlement.kind, CoinTransaction.Kind.FIXGEN_CHARGE)
        self.assertEqual(self._balance(), balance_before)

        # 額度已用掉：第二次觸發扣固定點數
        with_coins = charge_fixgen_generation(self.user, scan)
        self.assertEqual(with_coins.amount, -30)
        self.assertEqual(self._balance(), balance_before - 30)

    @override_settings(ARGUS_COIN_FIXGEN_GENERATION=7)
    def test_charge_price_comes_from_settings(self):
        scan = _make_scan(self.user)  # 無額度
        self._top_up(50)

        tx = charge_fixgen_generation(self.user, scan)

        self.assertEqual(tx.amount, -7)

    def test_charge_insufficient_coins_raises(self):
        scan = _make_scan(self.user)  # 無額度
        # 直接排光餘額（避開月贈點 signal 造成的變數）
        CoinWallet.objects.filter(user=self.user).update(balance=10)

        with self.assertRaises(InsufficientCoinError):
            charge_fixgen_generation(self.user, scan)

    def test_refund_restores_coins_idempotently(self):
        scan = _make_scan(self.user)
        self._top_up(100)
        charge_fixgen_generation(self.user, scan)
        balance_after_charge = CoinWallet.objects.get(user=self.user).balance

        refund = refund_fixgen_generation(self.user, scan)
        again = refund_fixgen_generation(self.user, scan)

        self.assertIsNotNone(refund)
        self.assertEqual(refund.amount, 30)
        self.assertEqual(refund.kind, CoinTransaction.Kind.FIXGEN_REFUND)
        self.assertIsNone(again)  # 冪等：第二次無可退
        self.assertEqual(
            CoinWallet.objects.get(user=self.user).balance,
            balance_after_charge + 30,
        )

    def test_refund_returns_entitlement_for_retry(self):
        scan = self._paid_scan()
        grant_fixgen_entitlement(self.user, scan)
        charge_fixgen_generation(self.user, scan)  # 消耗額度（0 元）
        self.assertFalse(fixgen_entitlement_available(self.user, scan))

        refund = refund_fixgen_generation(self.user, scan)

        self.assertIsNotNone(refund)
        self.assertEqual(refund.amount, 0)  # 額度返還，不是退點
        self.assertTrue(fixgen_entitlement_available(self.user, scan))
        # 重試可以再吃額度
        retry_charge = charge_fixgen_generation(self.user, scan)
        self.assertEqual(retry_charge.amount, 0)

    def test_is_paid_tier_auto_detection(self):
        fresh = User.objects.create_user(
            username="fresh-user", email="fresh@example.com", password="safe-test-password"
        )
        self.assertFalse(is_paid_tier(fresh))

        # 完成過付費掃描 → paid
        self._paid_scan()
        self.assertTrue(is_paid_tier(self.user))

        # 曾購點數包 → paid（total_purchased_ntd > 0）
        purchaser = User.objects.create_user(
            username="purchaser", email="purchaser@example.com", password="safe-test-password"
        )
        wallet = get_or_create_wallet(purchaser)
        CoinWallet.objects.filter(pk=wallet.pk).update(total_purchased_ntd=300)
        self.assertTrue(is_paid_tier(purchaser))
