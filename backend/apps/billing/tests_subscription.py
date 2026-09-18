"""輕量訂閱（SubscriptionPlan / UserSubscription）測試。

測試資料一律使用明顯假資料（example.com、safe-test-password 等）。
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import (
    CoinTransaction,
    CoinWallet,
    SubscriptionPlan,
    UserSubscription,
)
from apps.billing.services import (
    _advance_month,
    cancel_subscription,
    grant_subscription,
    settle_subscription,
)


def _make_user(username="sub-user"):
    return get_user_model().objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="safe-test-password",
    )


def _make_plan(code="sub-test", coins=300, price=199, active=True):
    return SubscriptionPlan.objects.create(
        code=code,
        name="測試訂閱方案",
        monthly_price_ntd=price,
        monthly_coins=coins,
        features=["每月點數", "測試用特色"],
        sort_order=99,
        is_active=active,
    )


class AdvanceMonthTests(APITestCase):
    """月份前進的日曆安全（31 號溢位夾到月末）。"""

    def test_january_31_advances_to_february_28(self):
        dt = timezone.datetime(2026, 1, 31, 10, 30, 0)
        self.assertEqual(_advance_month(dt), timezone.datetime(2026, 2, 28, 10, 30, 0))

    def test_leap_year_february_29_advances_to_march_29(self):
        dt = timezone.datetime(2028, 2, 29, 0, 0, 0)
        self.assertEqual(_advance_month(dt), timezone.datetime(2028, 3, 29, 0, 0, 0))

    def test_december_rolls_over_year(self):
        dt = timezone.datetime(2026, 12, 15, 8, 0, 0)
        self.assertEqual(_advance_month(dt), timezone.datetime(2027, 1, 15, 8, 0, 0))


class GrantSubscriptionTests(APITestCase):
    def setUp(self):
        self.user = _make_user("grant-user")
        self.plan = _make_plan("sub-grant", coins=500)

    def test_first_grant_sets_period_end_to_now(self):
        before = timezone.now()
        sub = grant_subscription(
            self.user, self.plan, 1, source=UserSubscription.Source.ADMIN_GRANT,
        )

        self.assertEqual(sub.status, UserSubscription.Status.ACTIVE)
        self.assertEqual(sub.periods_remaining, 1)
        self.assertGreaterEqual(sub.current_period_end, before)
        self.assertEqual(sub.last_grant_period, "")

    def test_second_grant_accumulates_periods(self):
        grant_subscription(self.user, self.plan, 1, source=UserSubscription.Source.ADMIN_GRANT)
        settle_subscription(self.user)  # 首期入帳，current_period_end 前進一個月

        grant_subscription(self.user, self.plan, 2, source=UserSubscription.Source.ADMIN_GRANT)

        sub = UserSubscription.objects.get(user=self.user)
        self.assertEqual(sub.periods_remaining, 2)  # 剩 0 + 新 2
        self.assertEqual(sub.plan, self.plan)

    def test_regrant_after_expiry_starts_from_now(self):
        grant_subscription(self.user, self.plan, 1, source=UserSubscription.Source.ADMIN_GRANT)
        settle_subscription(self.user)
        # 模擬期滿：把 current_period_end 推到過去再結算 → expired
        UserSubscription.objects.update(
            current_period_end=timezone.now() - timedelta(days=1),
        )
        settle_subscription(self.user)
        sub = UserSubscription.objects.get(user=self.user)
        self.assertEqual(sub.status, UserSubscription.Status.EXPIRED)

        regrant_before = timezone.now()
        sub = grant_subscription(
            self.user, self.plan, 1, source=UserSubscription.Source.ADMIN_GRANT,
        )

        self.assertEqual(sub.status, UserSubscription.Status.ACTIVE)
        self.assertEqual(sub.periods_remaining, 1)
        # 新一輪從 now 重新起算（不回填過去期數）
        self.assertGreaterEqual(sub.current_period_end, regrant_before)
        self.assertIsNone(sub.cancelled_at)

    def test_grant_rejects_non_positive_periods(self):
        with self.assertRaises(ValueError):
            grant_subscription(
                self.user, self.plan, 0, source=UserSubscription.Source.ADMIN_GRANT,
            )


class SettleSubscriptionTests(APITestCase):
    def setUp(self):
        self.user = _make_user("settle-user")
        self.plan = _make_plan("sub-settle", coins=300)

    def _grant_tx_count(self) -> int:
        return CoinTransaction.objects.filter(
            wallet__user=self.user,
            kind=CoinTransaction.Kind.SUBSCRIPTION_GRANT,
        ).count()

    def test_settle_grants_due_period_with_transaction(self):
        grant_subscription(self.user, self.plan, 1, source=UserSubscription.Source.ADMIN_GRANT)

        granted = settle_subscription(self.user)

        self.assertEqual(len(granted), 1)
        tx = granted[0]
        self.assertEqual(tx.amount, 300)
        self.assertEqual(tx.kind, CoinTransaction.Kind.SUBSCRIPTION_GRANT)
        self.assertIn("測試訂閱方案", tx.note)
        wallet = CoinWallet.objects.get(user=self.user)
        self.assertEqual(tx.balance_after, wallet.balance)
        sub = UserSubscription.objects.get(user=self.user)
        self.assertEqual(sub.periods_remaining, 0)
        self.assertEqual(
            sub.last_grant_period,
            f"{timezone.now().year}-{timezone.now().month:02d}",
        )
        # current_period_end 前進一個月（仍在未來 → 尚未 expired）
        self.assertGreater(sub.current_period_end, timezone.now())
        self.assertEqual(sub.status, UserSubscription.Status.ACTIVE)

    def test_settle_is_idempotent_within_same_month(self):
        grant_subscription(self.user, self.plan, 1, source=UserSubscription.Source.ADMIN_GRANT)
        settle_subscription(self.user)
        balance_after_first = self.user.coin_wallet.balance

        granted_again = settle_subscription(self.user)

        self.assertEqual(granted_again, [])
        self.assertEqual(self._grant_tx_count(), 1)
        self.assertEqual(self.user.coin_wallet.balance, balance_after_first)

    def test_periods_exhausted_then_expired_and_no_more_grants(self):
        grant_subscription(self.user, self.plan, 1, source=UserSubscription.Source.ADMIN_GRANT)
        settle_subscription(self.user)
        # 模擬時間流逝到期滿之後
        UserSubscription.objects.update(
            current_period_end=timezone.now() - timedelta(days=1),
        )

        granted = settle_subscription(self.user)

        self.assertEqual(granted, [])
        self.assertEqual(self._grant_tx_count(), 1)
        sub = UserSubscription.objects.get(user=self.user)
        self.assertEqual(sub.status, UserSubscription.Status.EXPIRED)
        # expired 後再呼叫維持不變
        self.assertEqual(settle_subscription(self.user), [])
        self.assertEqual(self._grant_tx_count(), 1)

    def test_multi_month_catchup_grants_each_period(self):
        grant_subscription(self.user, self.plan, 3, source=UserSubscription.Source.ADMIN_GRANT)
        settle_subscription(self.user)  # 首期立即入帳
        # 模擬兩個多月未登入（時間前進，而非把邊界拉回過去）
        future = timezone.now() + timedelta(days=65)

        with patch("apps.billing.services.timezone.now", return_value=future):
            granted = settle_subscription(self.user)

        self.assertEqual(len(granted), 2)  # 本次補發 2 期（首期已於先前入帳）
        self.assertEqual(self._grant_tx_count(), 3)
        sub = UserSubscription.objects.get(user=self.user)
        self.assertEqual(sub.periods_remaining, 0)
        self.assertEqual(
            CoinWallet.objects.get(user=self.user).balance,
            200 + 300 * 3,  # 月贈點 + 3 期
        )

    def test_cancel_before_boundary_grants_no_new_period(self):
        grant_subscription(self.user, self.plan, 2, source=UserSubscription.Source.ADMIN_GRANT)
        settle_subscription(self.user)  # 第 1 期入帳；下一邊界在 +1 個月
        balance_before = CoinWallet.objects.get(user=self.user).balance
        cancel_subscription(self.user)

        # 模擬期滿之後才又登入觸發 settle
        future = timezone.now() + timedelta(days=40)
        with patch("apps.billing.services.timezone.now", return_value=future):
            granted = settle_subscription(self.user)

        self.assertEqual(granted, [])  # 取消後到期的新期不發
        self.assertEqual(self._grant_tx_count(), 1)
        self.assertEqual(
            CoinWallet.objects.get(user=self.user).balance,
            balance_before,  # 當期權益保留不收回
        )

    def test_cancel_after_period_started_still_grants_that_period(self):
        grant_subscription(self.user, self.plan, 1, source=UserSubscription.Source.ADMIN_GRANT)
        cancel_subscription(self.user)  # 當前期（current_period_end=now）取消時已開始

        granted = settle_subscription(self.user)

        self.assertEqual(len(granted), 1)  # 已開始的當期仍可領
        sub = UserSubscription.objects.get(user=self.user)
        self.assertEqual(sub.status, UserSubscription.Status.CANCELLED)
        self.assertEqual(self._grant_tx_count(), 1)
        # 領完後不再發
        self.assertEqual(settle_subscription(self.user), [])
        self.assertEqual(self._grant_tx_count(), 1)

    def test_cancel_is_idempotent(self):
        grant_subscription(self.user, self.plan, 1, source=UserSubscription.Source.ADMIN_GRANT)
        first = cancel_subscription(self.user)
        cancelled_at = first.cancelled_at

        second = cancel_subscription(self.user)

        self.assertEqual(second.status, UserSubscription.Status.CANCELLED)
        self.assertEqual(second.cancelled_at, cancelled_at)

    def test_settle_without_subscription_is_noop(self):
        self.assertEqual(settle_subscription(self.user), [])
        self.assertIsNone(cancel_subscription(self.user))


class SubscriptionAPITests(APITestCase):
    def setUp(self):
        self.user = _make_user("api-user")
        self.client.force_authenticate(self.user)
        self.plan = _make_plan("sub-api", coins=300)

    def test_plans_endpoint_is_public_and_lists_active_only(self):
        _make_plan("sub-inactive", active=False)

        response = self.client.get(reverse("billing-subscription-plans"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [p["code"] for p in response.data["plans"]]
        self.assertIn("sub-api", codes)
        self.assertNotIn("sub-inactive", codes)
        self.assertIn("payment_mode", response.data)

    def test_my_subscription_returns_null_when_absent(self):
        response = self.client.get(reverse("billing-subscription"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["subscription"])

    @override_settings(ARGUS_PAYMENT_MODE="disabled")
    def test_subscribe_returns_503_when_payment_disabled(self):
        response = self.client.post(
            reverse("billing-subscribe"),
            {"plan_code": "sub-api"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(UserSubscription.objects.filter(user=self.user).exists())
        self.assertFalse(
            CoinTransaction.objects.filter(
                wallet__user=self.user,
                kind=CoinTransaction.Kind.SUBSCRIPTION_GRANT,
            ).exists(),
        )

    @override_settings(ARGUS_PAYMENT_MODE="ecpay_test")
    def test_subscribe_ecpay_test_grants_first_month_coins(self):
        response = self.client.post(
            reverse("billing-subscribe"),
            {"plan_code": "sub-api"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        sub = UserSubscription.objects.get(user=self.user)
        self.assertEqual(sub.status, UserSubscription.Status.ACTIVE)
        self.assertEqual(sub.source, UserSubscription.Source.ECPAY_TEST)
        self.assertEqual(sub.periods_remaining, 0)  # 首月已結算
        tx = CoinTransaction.objects.get(
            wallet__user=self.user,
            kind=CoinTransaction.Kind.SUBSCRIPTION_GRANT,
        )
        self.assertEqual(tx.amount, 300)  # monthly_coins
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 200 + 300)
        self.assertEqual(response.data["subscription"]["plan_code"], "sub-api")

    @override_settings(ARGUS_PAYMENT_MODE="ecpay_test")
    def test_subscribe_unknown_plan_returns_400(self):
        response = self.client.post(
            reverse("billing-subscribe"),
            {"plan_code": "no-such-plan"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(ARGUS_PAYMENT_MODE="ecpay_test")
    def test_cancel_endpoint_marks_cancelled_and_404_when_absent(self):
        self.client.post(reverse("billing-subscribe"), {"plan_code": "sub-api"}, format="json")

        response = self.client.post(reverse("billing-subscription-cancel"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["subscription"]["status"],
            UserSubscription.Status.CANCELLED,
        )

        # 取消後再查詢：狀態正確
        query = self.client.get(reverse("billing-subscription"))
        self.assertEqual(query.data["subscription"]["status"], UserSubscription.Status.CANCELLED)

    def test_cancel_endpoint_404_when_no_subscription(self):
        response = self.client.post(reverse("billing-subscription-cancel"))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(ARGUS_PAYMENT_MODE="ecpay_test")
    def test_wallet_entry_triggers_lazy_settle(self):
        self.client.post(reverse("billing-subscribe"), {"plan_code": "sub-api"}, format="json")
        # 模擬再買一期未入帳（admin 加碼），且時間前進到期滿之後
        grant_subscription(
            self.user, self.plan, 1, source=UserSubscription.Source.ADMIN_GRANT,
        )
        future = timezone.now() + timedelta(days=40)

        with patch("apps.billing.services.timezone.now", return_value=future):
            response = self.client.get(reverse("billing-wallet"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # lazy 結算把到期期數補發（200 月贈點 + 300 首月 + 300 補發）
        self.assertEqual(response.data["balance"], 200 + 300 + 300)
