"""訂閱實際扣款：綠界信用卡定期定額（委託建立、首期／每月扣款通知、取消、刪帳號）。

測試資料一律使用明顯假資料；綠界 API 呼叫全部 mock，不連外。
"""

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import httpx
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.ecpay import (
    build_check_mac_value,
    merchant_trade_no,
    parse_trade_no,
    subscription_trade_no,
)
from apps.billing.models import (
    CoinTransaction,
    CoinWallet,
    SubscriptionCharge,
    SubscriptionOrder,
    SubscriptionPlan,
    UserSubscription,
)
from apps.billing.services import settle_subscription
from apps.billing.tests import ECPAY_TEST_SETTINGS

PERIOD_POST = "apps.billing.ecpay.httpx.post"


def _sign(payload):
    payload["CheckMacValue"] = build_check_mac_value(
        payload,
        hash_key=ECPAY_TEST_SETTINGS["ECPAY_HASH_KEY"],
        hash_iv=ECPAY_TEST_SETTINGS["ECPAY_HASH_IV"],
    )
    return payload


def _ecpay_response(text):
    response = MagicMock()
    response.text = text
    response.raise_for_status.return_value = None
    return response


class TradeNoTests(APITestCase):
    def test_purchase_and_subscription_numbers_never_collide(self):
        self.assertEqual(parse_trade_no(merchant_trade_no(7)), ("purchase", 7))
        self.assertEqual(parse_trade_no(subscription_trade_no(7)), ("subscription", 7))
        self.assertEqual(len(subscription_trade_no(7)), 20)
        for bad in ("", "ARGUS", "ARGUSX0000000000000001", "OTHER000000000000001"):
            self.assertIsNone(parse_trade_no(bad))


@override_settings(**ECPAY_TEST_SETTINGS)
class RecurringSubscriptionTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="rec@example.com", email="rec@example.com", password="safe-test-password"
        )
        self.client.force_authenticate(self.user)
        self.plan = SubscriptionPlan.objects.create(
            code="sub-rec", name="測試月訂閱", monthly_price_ntd=299, monthly_coins=500,
        )

    def subscribe(self, **extra):
        body = {
            "plan_code": "sub-rec", "buyer_name": "王小明", "buyer_email": "rec@example.com",
            "invoice_type": "personal", "agree_terms": True, **extra,
        }
        return self.client.post(reverse("billing-subscribe"), body, format="json")

    def first_charge(self, order, **overrides):
        payload = {
            "MerchantID": ECPAY_TEST_SETTINGS["ECPAY_MERCHANT_ID"],
            "MerchantTradeNo": subscription_trade_no(order.id),
            "RtnCode": "1", "RtnMsg": "Succeeded", "TradeAmt": str(order.price_ntd),
            "TradeNo": "first-0001", "PaymentDate": "2026/10/04 12:00:00",
            "PaymentType": "Credit_CreditCard", "SimulatePaid": "0", **overrides,
        }
        return self.client.post(reverse("billing-ecpay-callback"), _sign(payload))

    def period_charge(self, order, times, **overrides):
        payload = {
            "MerchantID": ECPAY_TEST_SETTINGS["ECPAY_MERCHANT_ID"],
            "MerchantTradeNo": subscription_trade_no(order.id),
            "RtnCode": "1", "RtnMsg": "Succeeded", "PeriodType": "M", "Frequency": "1",
            "ExecTimes": str(order.exec_times), "Amount": str(order.price_ntd),
            "gwsr": f"9{times:05d}", "ProcessDate": "2026/11/04 03:00:00", "AuthCode": "777777",
            "FirstAuthAmount": str(order.price_ntd), "TotalSuccessTimes": str(times),
            "SimulatePaid": "0", **overrides,
        }
        return self.client.post(reverse("billing-ecpay-period-callback"), _sign(payload))

    def balance(self):
        return CoinWallet.objects.get(user=self.user).balance

    def active_order(self):
        response = self.subscribe()
        self.assertEqual(response.status_code, 201)
        order = SubscriptionOrder.objects.get(pk=response.data["order"]["id"])
        self.assertEqual(self.first_charge(order).content, b"1|OK")
        order.refresh_from_db()
        return order

    def test_subscribe_returns_recurring_checkout_without_granting(self):
        response = self.subscribe()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        fields = response.data["payment"]["fields"]
        self.assertEqual(
            response.data["payment"]["action"], ECPAY_TEST_SETTINGS["ECPAY_CHECKOUT_URL"]
        )
        self.assertEqual(fields["PeriodAmount"], fields["TotalAmount"])
        self.assertEqual(fields["TotalAmount"], "299")
        self.assertEqual((fields["PeriodType"], fields["Frequency"]), ("M", "1"))
        self.assertGreaterEqual(int(fields["ExecTimes"]), 2)
        self.assertEqual(fields["PeriodReturnURL"], ECPAY_TEST_SETTINGS["ECPAY_PERIOD_RETURN_URL"])
        self.assertEqual(fields["CheckMacValue"], _sign(dict(fields))["CheckMacValue"])
        self.assertFalse(UserSubscription.objects.filter(user=self.user).exists())
        self.assertEqual(self.balance(), 200)

    def test_subscribe_requires_invoice_details(self):
        response = self.client.post(
            reverse("billing-subscribe"), {"plan_code": "sub-rec"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("buyer_email", response.data)

    def test_first_charge_activates_once_and_grants_first_month(self):
        order = self.active_order()
        # 綠界重送同一則通知：不重複發點
        self.assertEqual(self.first_charge(order).content, b"1|OK")

        self.assertEqual(order.status, SubscriptionOrder.Status.ACTIVE)
        self.assertEqual(self.balance(), 200 + 500)
        sub = UserSubscription.objects.get(user=self.user)
        self.assertEqual(sub.source, UserSubscription.Source.ECPAY_TEST)
        self.assertEqual(SubscriptionCharge.objects.filter(order=order, succeeded=True).count(), 1)
        mine = self.client.get(reverse("billing-subscription")).data["subscription"]
        self.assertTrue(mine["auto_renew"])

    def test_rejected_notifications_do_not_grant(self):
        order = SubscriptionOrder.objects.get(pk=self.subscribe().data["order"]["id"])
        bad_mac = self.first_charge(order)  # 先送一則正確的，再測錯誤的都不影響
        self.assertEqual(bad_mac.content, b"1|OK")
        start = self.balance()
        forged = _sign({
            "MerchantID": ECPAY_TEST_SETTINGS["ECPAY_MERCHANT_ID"],
            "MerchantTradeNo": subscription_trade_no(order.id), "RtnCode": "1",
            "Amount": "299", "TotalSuccessTimes": "2", "SimulatePaid": "0",
        })
        forged["CheckMacValue"] = "0" * 64
        cases = (
            forged,
            _sign({**{k: v for k, v in forged.items() if k != "CheckMacValue"}, "Amount": "1"}),
            _sign({**{k: v for k, v in forged.items() if k != "CheckMacValue"},
                   "MerchantID": "someone-else"}),
        )
        for payload in cases:
            response = self.client.post(reverse("billing-ecpay-period-callback"), payload)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.period_charge(order, 2, SimulatePaid="1").content, b"1|OK")
        self.assertEqual(self.balance(), start)

    def test_first_charge_failure_marks_failed_without_coins(self):
        order = SubscriptionOrder.objects.get(pk=self.subscribe().data["order"]["id"])
        self.first_charge(order, RtnCode="10100058", RtnMsg="授權失敗")
        order.refresh_from_db()
        self.assertEqual(order.status, SubscriptionOrder.Status.FAILED)
        self.assertEqual(self.balance(), 200)
        self.assertFalse(UserSubscription.objects.filter(user=self.user).exists())

    def test_monthly_charges_add_periods_idempotently(self):
        order = self.active_order()
        later = timezone.now() + timedelta(days=32)
        with patch("apps.billing.services.timezone.now", return_value=later):
            self.assertEqual(self.period_charge(order, 2).content, b"1|OK")
            self.assertEqual(self.period_charge(order, 2).content, b"1|OK")  # 重送
            settle_subscription(self.user)
        self.assertEqual(self.balance(), 200 + 500 + 500)
        self.assertEqual(
            CoinTransaction.objects.filter(
                wallet__user=self.user, kind=CoinTransaction.Kind.SUBSCRIPTION_GRANT
            ).count(),
            2,
        )
        # 某期扣款失敗：只留紀錄
        self.period_charge(order, 2, RtnCode="10100050", RtnMsg="額度不足")
        self.assertEqual(SubscriptionCharge.objects.filter(order=order, succeeded=False).count(), 1)
        self.assertEqual(self.balance(), 200 + 1000)

    def test_auto_renew_gets_grace_before_expiring(self):
        self.active_order()
        just_after = timezone.now() + timedelta(days=32)
        with patch("apps.billing.services.timezone.now", return_value=just_after):
            settle_subscription(self.user)
        self.assertEqual(
            UserSubscription.objects.get(user=self.user).status, UserSubscription.Status.ACTIVE
        )
        long_after = timezone.now() + timedelta(days=40)
        with patch("apps.billing.services.timezone.now", return_value=long_after):
            settle_subscription(self.user)
        self.assertEqual(
            UserSubscription.objects.get(user=self.user).status, UserSubscription.Status.EXPIRED
        )

    def test_second_subscription_while_auto_renewing_is_rejected(self):
        self.active_order()
        self.assertEqual(self.subscribe().status_code, status.HTTP_409_CONFLICT)

    def test_cancel_calls_ecpay_then_cancels_locally(self):
        order = self.active_order()
        reply = _sign({
            "MerchantID": ECPAY_TEST_SETTINGS["ECPAY_MERCHANT_ID"],
            "MerchantTradeNo": subscription_trade_no(order.id), "RtnCode": "1", "RtnMsg": "成功",
        })
        text = "&".join(f"{k}={v}" for k, v in reply.items())
        with patch(PERIOD_POST, return_value=_ecpay_response(text)) as post:
            response = self.client.post(reverse("billing-subscription-cancel"))

        self.assertEqual(response.status_code, 200)
        sent = post.call_args.kwargs["data"]
        self.assertEqual(post.call_args.args[0], ECPAY_TEST_SETTINGS["ECPAY_PERIOD_ACTION_URL"])
        self.assertEqual((sent["Action"], sent["MerchantTradeNo"]), ("Cancel", order.merchant_no))
        order.refresh_from_db()
        self.assertEqual(order.status, SubscriptionOrder.Status.CANCELLED)
        self.assertEqual(response.data["subscription"]["status"], "cancelled")
        self.assertFalse(response.data["subscription"]["auto_renew"])

    def test_cancel_failure_keeps_subscription_and_charging_state(self):
        order = self.active_order()
        with patch(PERIOD_POST, side_effect=[
            _ecpay_response("RtnCode=10100248&RtnMsg=error"),
            _ecpay_response(json.dumps({"MerchantTradeNo": order.merchant_no, "ExecStatus": "1"})),
        ]):
            response = self.client.post(reverse("billing-subscription-cancel"))
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        order.refresh_from_db()
        self.assertEqual(order.status, SubscriptionOrder.Status.ACTIVE)
        self.assertEqual(
            UserSubscription.objects.get(user=self.user).status, UserSubscription.Status.ACTIVE
        )

    def test_cancel_succeeds_when_ecpay_already_terminated(self):
        order = self.active_order()
        with patch(PERIOD_POST, side_effect=[
            _ecpay_response("RtnCode=10100248&RtnMsg=error"),
            _ecpay_response(json.dumps({"MerchantTradeNo": order.merchant_no, "ExecStatus": "0"})),
        ]):
            response = self.client.post(reverse("billing-subscription-cancel"))
        self.assertEqual(response.status_code, 200)

    def test_account_deletion_stops_charges_first(self):
        order = self.active_order()
        self.client.force_authenticate(self.user)
        with patch(PERIOD_POST, side_effect=httpx.ConnectError("down")):
            blocked = self.client.post(
                "/api/auth/me/delete/",
                {"password": "safe-test-password", "confirm": "刪除帳號"}, format="json",
            )
        self.assertEqual(blocked.status_code, 403)
        self.assertTrue(get_user_model().objects.get(pk=self.user.pk).is_active)

        reply = _sign({
            "MerchantID": ECPAY_TEST_SETTINGS["ECPAY_MERCHANT_ID"],
            "MerchantTradeNo": order.merchant_no, "RtnCode": "1", "RtnMsg": "成功",
        })
        text = "&".join(f"{k}={v}" for k, v in reply.items())
        with patch(PERIOD_POST, return_value=_ecpay_response(text)):
            deleted = self.client.post(
                "/api/auth/me/delete/",
                {"password": "safe-test-password", "confirm": "刪除帳號"}, format="json",
            )
        self.assertEqual(deleted.status_code, 204)
        order.refresh_from_db()
        self.assertEqual(order.status, SubscriptionOrder.Status.CANCELLED)
        self.assertEqual(order.buyer_name, "已刪除用戶")
