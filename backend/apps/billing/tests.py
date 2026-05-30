from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import CoinTransaction, CoinWallet, PricingPlan
from apps.billing.services import (
    InsufficientCoinError,
    admin_adjust,
    estimate_scan_cost,
    grant_monthly_bonus_if_needed,
    hold_for_scan,
    purchase_plan,
    refund_full_for_scan,
    settle_scan_actual,
)
from apps.scans.models import ScanJob


def _make_user(username="alice", email=None):
    return get_user_model().objects.create_user(
        username=username,
        email=email or f"{username}@example.com",
        password="safe-test-password",
    )


def _make_scan(user, max_pages=10):
    return ScanJob.objects.create(
        user=user,
        original_url="https://example.com/",
        normalized_url="https://example.com/",
        origin="https://example.com",
        max_pages=max_pages,
    )


class WalletSignalTests(APITestCase):
    """建立 user 時的 signal 行為：自動建錢包 + 首月贈點。"""

    def test_wallet_auto_created_on_user_creation(self):
        user = _make_user("bob")
        self.assertTrue(hasattr(user, "coin_wallet"))
        self.assertEqual(user.coin_wallet.balance, 200)

    def test_first_monthly_bonus_transaction_recorded(self):
        user = _make_user("carol")
        tx = user.coin_wallet.transactions.get()
        self.assertEqual(tx.amount, 200)
        self.assertEqual(tx.kind, CoinTransaction.Kind.MONTHLY_BONUS)
        self.assertEqual(tx.balance_after, 200)

    def test_grant_monthly_bonus_is_idempotent_in_same_month(self):
        user = _make_user("dave")
        # signal 已發過一次；同月再呼叫不應再發
        again = grant_monthly_bonus_if_needed(user)
        self.assertIsNone(again)
        self.assertEqual(user.coin_wallet.balance, 200)
        self.assertEqual(user.coin_wallet.transactions.count(), 1)


class CostEstimationTests(APITestCase):
    def test_estimate_uses_max_pages_times_coin_per_page(self):
        self.assertEqual(estimate_scan_cost(10), 100)
        self.assertEqual(estimate_scan_cost(50), 500)


class ScanHoldRefundTests(APITestCase):
    def setUp(self):
        self.user = _make_user("eve")
        # 預先補到 1000 coin 方便測試
        admin_adjust(target_user=self.user, delta=800,
                     admin_actor=None, note="測試補點")

    def test_hold_deducts_balance_and_creates_transaction(self):
        scan = _make_scan(self.user, max_pages=10)
        hold_for_scan(self.user, scan)
        wallet = CoinWallet.objects.get(user=self.user)
        # 原 200 + 800 = 1000，扣 100 後 = 900
        self.assertEqual(wallet.balance, 900)
        tx = scan.coin_transactions.get(kind=CoinTransaction.Kind.SCAN_HOLD)
        self.assertEqual(tx.amount, -100)
        self.assertEqual(tx.balance_after, 900)

    def test_hold_raises_when_insufficient(self):
        scan = _make_scan(self.user, max_pages=200)  # 需 2000 coin，有 1000
        with self.assertRaises(InsufficientCoinError):
            hold_for_scan(self.user, scan)

    def test_full_refund_on_failure_restores_balance(self):
        scan = _make_scan(self.user, max_pages=10)
        hold_for_scan(self.user, scan)  # 餘額 900
        refund_full_for_scan(self.user, scan, reason="失敗")
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 1000)
        refund_tx = scan.coin_transactions.filter(
            kind=CoinTransaction.Kind.SCAN_REFUND
        ).get()
        self.assertEqual(refund_tx.amount, 100)

    def test_full_refund_is_idempotent(self):
        scan = _make_scan(self.user, max_pages=10)
        hold_for_scan(self.user, scan)
        refund_full_for_scan(self.user, scan, reason="失敗")
        # 第二次呼叫不應再退
        again = refund_full_for_scan(self.user, scan, reason="失敗")
        self.assertIsNone(again)

    def test_settle_actual_refunds_difference_and_counts_scan(self):
        scan = _make_scan(self.user, max_pages=50)  # 預扣 500
        hold_for_scan(self.user, scan)
        # 實際只爬了 30 頁 → 退回 (50-30)*10 = 200
        settle_scan_actual(self.user, scan, actual_pages=30)
        wallet = CoinWallet.objects.get(user=self.user)
        # 原 1000 - 500 (hold) + 200 (refund) = 700
        self.assertEqual(wallet.balance, 700)
        self.assertEqual(wallet.total_scans_used, 1)


class PurchaseTests(APITestCase):
    def setUp(self):
        self.user = _make_user("frank")

    def test_purchase_plan_adds_coins_and_accumulates_ntd(self):
        plan = PricingPlan.objects.get(code="standard")
        purchase_plan(self.user, plan)
        wallet = CoinWallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, 200 + plan.coin_amount)  # 200 月贈 + 500
        self.assertEqual(wallet.total_purchased_ntd, plan.price_ntd)
        tx = wallet.transactions.get(kind=CoinTransaction.Kind.PURCHASE)
        self.assertEqual(tx.amount, plan.coin_amount)
        self.assertEqual(tx.plan, plan)

    def test_seeded_plans_match_specification(self):
        codes = list(
            PricingPlan.objects.values_list("code", flat=True).order_by("sort_order")
        )
        self.assertEqual(codes, ["starter", "standard", "advanced", "flagship"])
        self.assertEqual(
            PricingPlan.objects.get(code="flagship").coin_amount, 2200,
        )

    def test_pricing_plans_are_public_for_purchase_page(self):
        response = self.client.get(reverse("billing-plans"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("plans", response.data)

    def test_dev_cheat_route_is_removed(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/billing/dev-cheat/",
            {"mode": "set_max"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AdminAdjustTests(APITestCase):
    def setUp(self):
        self.user = _make_user("grace")

    def test_admin_adjust_can_add_or_deduct(self):
        admin_adjust(target_user=self.user, delta=300,
                     admin_actor=None, note="退費")
        wallet = CoinWallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, 500)

        admin_adjust(target_user=self.user, delta=-100,
                     admin_actor=None, note="罰扣")
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 400)

    def test_admin_adjust_clamps_to_zero_no_negative_balance(self):
        # 原 200，扣 -500 → 應該夾到 0，且 transaction.amount = -200
        tx = admin_adjust(target_user=self.user, delta=-500,
                          admin_actor=None, note="超扣測試")
        self.assertEqual(tx.amount, -200)
        self.assertEqual(tx.balance_after, 0)
        self.assertEqual(CoinWallet.objects.get(user=self.user).balance, 0)


@override_settings(ARGUS_AUTO_QUEUE_SCANS=False)
class BillingAPITests(APITestCase):
    def setUp(self):
        self.user = _make_user("henry")
        self.client.force_authenticate(self.user)

    def test_wallet_endpoint_returns_balance_and_recent_transactions(self):
        response = self.client.get(reverse("billing-wallet"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["balance"], 200)
        self.assertEqual(response.data["coin_per_page"], 10)
        self.assertEqual(len(response.data["recent_transactions"]), 1)

    def test_plans_endpoint_returns_four_active_plans(self):
        response = self.client.get(reverse("billing-plans"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["plans"]), 4)
        codes = [p["code"] for p in response.data["plans"]]
        self.assertEqual(codes, ["starter", "standard", "advanced", "flagship"])

    def _valid_purchase_payload(self, **overrides):
        payload = {
            "plan_code": "starter",
            "buyer_name": "王小明",
            "buyer_email": "buyer@example.com",
            "invoice_type": "personal",
            "agree_terms": True,
        }
        payload.update(overrides)
        return payload

    def test_purchase_endpoint_adds_coins(self):
        response = self.client.post(
            reverse("billing-purchase"),
            self._valid_purchase_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # 3 步驟結帳：回傳 wallet + order，餘額在 wallet 物件內
        self.assertEqual(response.data["wallet"]["balance"], 300)  # 200 + 100
        self.assertEqual(response.data["order"]["status"], "paid")
        self.assertEqual(response.data["order"]["coin_amount"], 100)

    def test_purchase_endpoint_rejects_unknown_plan(self):
        response = self.client.post(
            reverse("billing-purchase"),
            self._valid_purchase_payload(plan_code="non_existent"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(ARGUS_AUTO_QUEUE_SCANS=False)
class PurchaseOrderTests(APITestCase):
    """3 步驟結帳 wizard 對應的 PurchaseOrder 行為。"""

    def setUp(self):
        self.user = _make_user("orderer")
        self.client.force_authenticate(self.user)

    def _payload(self, **overrides):
        payload = {
            "plan_code": "standard",
            "buyer_name": "陳大文",
            "buyer_email": "chen@example.com",
            "invoice_type": "personal",
            "agree_terms": True,
        }
        payload.update(overrides)
        return payload

    def test_personal_invoice_creates_paid_order_with_snapshot(self):
        from apps.billing.models import PurchaseOrder
        response = self.client.post(
            reverse("billing-purchase"), self._payload(), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = PurchaseOrder.objects.get(user=self.user)
        # 價格與 coin 快照寫入訂單，後續方案改動不會影響此訂單
        self.assertEqual(order.price_ntd, 450)
        self.assertEqual(order.coin_amount, 500)
        self.assertEqual(order.status, PurchaseOrder.Status.PAID)
        self.assertEqual(order.invoice_type, PurchaseOrder.InvoiceType.PERSONAL)
        # 個人發票不應留下公司資訊
        self.assertEqual(order.company_name, "")
        self.assertEqual(order.tax_id, "")
        # 訂單連結到入帳交易
        self.assertIsNotNone(order.transaction)
        self.assertEqual(order.transaction.amount, 500)
        self.assertIsNotNone(order.paid_at)

    def test_company_invoice_requires_company_name(self):
        response = self.client.post(
            reverse("billing-purchase"),
            self._payload(
                invoice_type="company",
                company_name="",
                tax_id="12345678",
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("company_name", response.data)

    def test_company_invoice_requires_8_digit_tax_id(self):
        response = self.client.post(
            reverse("billing-purchase"),
            self._payload(
                invoice_type="company",
                company_name="Acme Co.",
                tax_id="ABC123",  # 不是 8 碼數字
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tax_id", response.data)

    def test_company_invoice_with_valid_data_stored(self):
        from apps.billing.models import PurchaseOrder
        response = self.client.post(
            reverse("billing-purchase"),
            self._payload(
                invoice_type="company",
                company_name="Acme 有限公司",
                tax_id="12345678",
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = PurchaseOrder.objects.get(user=self.user)
        self.assertEqual(order.invoice_type, PurchaseOrder.InvoiceType.COMPANY)
        self.assertEqual(order.company_name, "Acme 有限公司")
        self.assertEqual(order.tax_id, "12345678")

    def test_agree_terms_must_be_true(self):
        response = self.client.post(
            reverse("billing-purchase"),
            self._payload(agree_terms=False),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("agree_terms", response.data)

    def test_my_orders_returns_user_orders(self):
        # 建兩單
        self.client.post(reverse("billing-purchase"), self._payload(), format="json")
        self.client.post(
            reverse("billing-purchase"),
            self._payload(plan_code="starter"),
            format="json",
        )
        response = self.client.get(reverse("billing-orders"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["orders"]), 2)

    def test_personal_invoice_accepts_mobile_barcode(self):
        from apps.billing.models import PurchaseOrder
        response = self.client.post(
            reverse("billing-purchase"),
            self._payload(carrier_type="mobile_barcode", carrier_id="/AB12CDE"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = PurchaseOrder.objects.get(user=self.user)
        self.assertEqual(order.carrier_type, "mobile_barcode")
        self.assertEqual(order.carrier_id, "/AB12CDE")

    def test_mobile_barcode_invalid_format_rejected(self):
        response = self.client.post(
            reverse("billing-purchase"),
            self._payload(carrier_type="mobile_barcode", carrier_id="ABCD1234"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("carrier_id", response.data)

    def test_personal_invoice_accepts_citizen_digital(self):
        from apps.billing.models import PurchaseOrder
        response = self.client.post(
            reverse("billing-purchase"),
            self._payload(
                carrier_type="citizen_digital",
                carrier_id="AB12345678901234",
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = PurchaseOrder.objects.get(user=self.user)
        self.assertEqual(order.carrier_type, "citizen_digital")
        self.assertEqual(order.carrier_id, "AB12345678901234")

    def test_citizen_digital_invalid_rejected(self):
        response = self.client.post(
            reverse("billing-purchase"),
            self._payload(carrier_type="citizen_digital", carrier_id="abc123"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_company_invoice_ignores_carrier_fields(self):
        from apps.billing.models import PurchaseOrder
        response = self.client.post(
            reverse("billing-purchase"),
            self._payload(
                invoice_type="company",
                company_name="Acme",
                tax_id="12345678",
                carrier_type="mobile_barcode",
                carrier_id="/AB12CDE",  # 即使送了也會被清空
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = PurchaseOrder.objects.get(user=self.user)
        self.assertEqual(order.carrier_type, "cloud")  # 強制 cloud
        self.assertEqual(order.carrier_id, "")

    def test_my_orders_does_not_leak_other_users(self):
        other = _make_user("other")
        self.client.force_authenticate(other)
        self.client.post(reverse("billing-purchase"), self._payload(), format="json")
        # 切回 self.user，應該看不到 other 的訂單
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse("billing-orders"))
        self.assertEqual(len(response.data["orders"]), 0)


@override_settings(ARGUS_AUTO_QUEUE_SCANS=False)
class ScanCreateCoinIntegrationTests(APITestCase):
    """整合測試：建立掃描時的 coin 預扣與不足回應。"""

    def setUp(self):
        self.user = _make_user("ivy")
        self.client.force_authenticate(self.user)
        self.url = reverse("scan-list")

    def test_create_scan_holds_coins_on_success(self):
        # max_pages=10 → 預扣 100，使用者有 200，剩 100
        response = self.client.post(
            self.url,
            {
                "url": "https://example.com/",
                "authorization_confirmed": True,
                "max_pages": 10,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        wallet = CoinWallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, 100)
        scan = ScanJob.objects.get()
        self.assertEqual(scan.coin_transactions.count(), 1)

    def test_create_scan_rejected_when_insufficient_coins(self):
        # max_pages=50 → 預扣 500，使用者只有 200
        response = self.client.post(
            self.url,
            {
                "url": "https://example.com/",
                "authorization_confirmed": True,
                "max_pages": 50,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("coin", response.data)
        # 沒有建立 scan、餘額不變
        self.assertFalse(ScanJob.objects.exists())
        self.assertEqual(
            CoinWallet.objects.get(user=self.user).balance, 200,
        )

    def test_create_scan_rejects_pages_above_project_limit(self):
        response = self.client.post(
            self.url,
            {
                "url": "https://example.com/",
                "authorization_confirmed": True,
                "max_pages": 51,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("max_pages", response.data)
        self.assertFalse(ScanJob.objects.exists())

    def test_cancel_scan_refunds_held_coins(self):
        response = self.client.post(
            self.url,
            {
                "url": "https://example.com/",
                "authorization_confirmed": True,
                "max_pages": 10,
            },
            format="json",
        )
        scan_id = response.data["id"]
        self.assertEqual(
            CoinWallet.objects.get(user=self.user).balance, 100,
        )
        # 取消（status 預設為 queued，可被 cancel）
        cancel = self.client.post(reverse("scan-cancel", args=[scan_id]))
        self.assertEqual(cancel.status_code, status.HTTP_200_OK)
        self.assertEqual(
            CoinWallet.objects.get(user=self.user).balance, 200,
        )
