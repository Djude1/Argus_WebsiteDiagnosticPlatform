"""綠界全方位金流：簽章、結帳表單（購點一次付清／訂閱信用卡定期定額）與定期定額取消。

測試（payment-stage）與正式（payment）環境的網址由 settings.ARGUS_PAYMENT_MODE 決定，
這裡不寫死任何網址或金鑰。規格：
- 定期定額：PeriodAmount 必須等於 TotalAmount、ExecTimes 至少 2 次；首次授權通知 ReturnURL，
  第 2 期起每次授權通知 PeriodReturnURL（https://developers.ecpay.com.tw/2868/、/5631/）
- 取消：POST CreditCardPeriodAction，Action=Cancel（https://developers.ecpay.com.tw/2900/）
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

import httpx
from django.conf import settings
from django.utils import timezone


def build_check_mac_value(parameters: dict[str, object], *, hash_key: str, hash_iv: str) -> str:
    """依綠界規格排序、URL encode 後以 SHA256 產生大寫檢查碼。"""
    pairs = sorted(
        (str(key), str(value))
        for key, value in parameters.items()
        if key != "CheckMacValue"
    )
    raw_parameters = "&".join(f"{key}={value}" for key, value in pairs)
    raw = f"HashKey={hash_key}&{raw_parameters}&HashIV={hash_iv}"
    encoded = quote_plus(raw, safe="-_.!*()").replace("~", "%7e").lower()
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest().upper()


def verify_check_mac_value(parameters: dict[str, object]) -> bool:
    received = str(parameters.get("CheckMacValue", "")).upper()
    if not received:
        return False
    expected = build_check_mac_value(
        parameters,
        hash_key=settings.ECPAY_HASH_KEY,
        hash_iv=settings.ECPAY_HASH_IV,
    )
    return hmac.compare_digest(received, expected)


logger = logging.getLogger(__name__)

# 定期定額每月扣一次，最多 99 次（綠界上限 999；使用者隨時可取消）
SUBSCRIPTION_EXEC_TIMES = 99
_PURCHASE_PREFIX = "ARGUS"
_SUBSCRIPTION_PREFIX = "ARGUSS"


def merchant_trade_no(order_id: int) -> str:
    """購點訂單編號：ARGUS＋15 位數字（綠界上限 20 字元）。"""
    if order_id < 1 or order_id > 999_999_999_999_999:
        raise ValueError("訂單 ID 超出綠界 MerchantTradeNo 可表示範圍")
    return f"{_PURCHASE_PREFIX}{order_id:015d}"


def subscription_trade_no(order_id: int) -> str:
    """訂閱（定期定額）編號：ARGUSS＋14 位數字；第 6 字是 S，不會與購點編號混淆。"""
    if order_id < 1 or order_id > 99_999_999_999_999:
        raise ValueError("訂單 ID 超出綠界 MerchantTradeNo 可表示範圍")
    return f"{_SUBSCRIPTION_PREFIX}{order_id:014d}"


def parse_trade_no(trade_no: str) -> tuple[str, int] | None:
    """回傳 ("purchase"|"subscription", 訂單 id)；格式不符回 None。"""
    trade_no = trade_no or ""
    if trade_no.startswith(_SUBSCRIPTION_PREFIX) and len(trade_no) == 20:
        digits, kind = trade_no[len(_SUBSCRIPTION_PREFIX):], "subscription"
    elif trade_no.startswith(_PURCHASE_PREFIX) and len(trade_no) == 20:
        digits, kind = trade_no[len(_PURCHASE_PREFIX):], "purchase"
    else:
        return None
    if not digits.isdigit() or int(digits) < 1:
        return None
    return kind, int(digits)


def _client_back_url(**params: str) -> str:
    parsed = urlsplit(settings.ECPAY_CLIENT_BACK_URL)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


def _sign(fields: dict[str, str]) -> dict[str, str]:
    fields["CheckMacValue"] = build_check_mac_value(
        fields,
        hash_key=settings.ECPAY_HASH_KEY,
        hash_iv=settings.ECPAY_HASH_IV,
    )
    return fields


def build_checkout_fields(order) -> dict[str, str]:
    fields = {
        "MerchantID": settings.ECPAY_MERCHANT_ID,
        "MerchantTradeNo": merchant_trade_no(order.id),
        "MerchantTradeDate": timezone.localtime().strftime("%Y/%m/%d %H:%M:%S"),
        "PaymentType": "aio",
        "TotalAmount": str(order.price_ntd),
        "TradeDesc": "Argus 點數購買",
        "ItemName": f"{order.plan.name} {order.coin_amount} coin",
        "ReturnURL": settings.ECPAY_RETURN_URL,
        "ChoosePayment": "Credit",
        "EncryptType": "1",
        "ClientBackURL": _client_back_url(payment_return="1", order_id=str(order.id)),
        "NeedExtraPaidInfo": "N",
        "CustomField1": str(order.id),
    }
    return _sign(fields)


def build_subscription_checkout_fields(order) -> dict[str, str]:
    """訂閱：信用卡定期定額，每月扣一次 order.price_ntd（首期立即授權）。"""
    amount = str(order.price_ntd)
    fields = {
        "MerchantID": settings.ECPAY_MERCHANT_ID,
        "MerchantTradeNo": subscription_trade_no(order.id),
        "MerchantTradeDate": timezone.localtime().strftime("%Y/%m/%d %H:%M:%S"),
        "PaymentType": "aio",
        "TotalAmount": amount,
        "TradeDesc": "Argus 月訂閱",
        "ItemName": f"{order.plan.name} 月訂閱（每月 {order.monthly_coins} coin）",
        "ReturnURL": settings.ECPAY_RETURN_URL,
        "ChoosePayment": "Credit",
        "EncryptType": "1",
        "ClientBackURL": _client_back_url(subscription_return="1"),
        "NeedExtraPaidInfo": "N",
        "PeriodAmount": amount,
        "PeriodType": "M",
        "Frequency": "1",
        "ExecTimes": str(order.exec_times),
        "PeriodReturnURL": settings.ECPAY_PERIOD_RETURN_URL,
    }
    return _sign(fields)


class EcpayActionError(Exception):
    """呼叫綠界 API 失敗（網路、簽章或綠界回覆失敗）；訊息可直接顯示給使用者。"""


def cancel_period_order(order) -> None:
    """請綠界終止定期定額後續扣款；失敗丟 EcpayActionError（呼叫端不得把訂閱當成已取消）。"""
    fields = _sign({
        "MerchantID": settings.ECPAY_MERCHANT_ID,
        "MerchantTradeNo": subscription_trade_no(order.id),
        "Action": "Cancel",
        "TimeStamp": str(int(time.time())),
    })
    try:
        response = httpx.post(settings.ECPAY_PERIOD_ACTION_URL, data=fields, timeout=15)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("綠界定期定額取消呼叫失敗 order=%s", order.id)
        raise EcpayActionError("暫時無法連線綠界，請稍後再試。") from exc
    result = dict(parse_qsl(response.text.strip(), keep_blank_values=True))
    if "CheckMacValue" in result and not verify_check_mac_value(result):
        logger.warning("綠界定期定額取消回應簽章不符 order=%s", order.id)
        raise EcpayActionError("綠界回應驗證失敗，請稍後再試。")
    if result.get("RtnCode") != "1":
        # 已終止（0）或已執行完畢（2）的定期定額，綠界會拒絕再取消；這種情況等同已停止扣款
        if period_exec_status(order) in {"0", "2"}:
            return
        message = (result.get("RtnMsg") or "未知錯誤")[:100]
        logger.warning("綠界定期定額取消失敗 order=%s rtn=%s", order.id, result.get("RtnCode"))
        raise EcpayActionError(f"綠界拒絕取消：{message}")


def period_exec_status(order) -> str | None:
    """查詢定期定額狀態：ExecStatus "0"＝已終止、"1"＝執行中、"2"＝執行完成；查不到回 None。"""
    fields = _sign({
        "MerchantID": settings.ECPAY_MERCHANT_ID,
        "MerchantTradeNo": subscription_trade_no(order.id),
        "TimeStamp": str(int(time.time())),
    })
    query_url = settings.ECPAY_PERIOD_ACTION_URL.replace(
        "CreditCardPeriodAction", "QueryCreditCardPeriodInfo"
    )
    try:
        response = httpx.post(query_url, data=fields, timeout=15)
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("綠界定期定額查詢失敗 order=%s", order.id)
        return None
    text = response.text.strip()
    try:
        data = json.loads(text)
    except ValueError:
        data = dict(parse_qsl(text, keep_blank_values=True))
    if not isinstance(data, dict):
        return None
    if str(data.get("MerchantTradeNo", "")) != fields["MerchantTradeNo"]:
        return None
    status = data.get("ExecStatus")
    return None if status is None else str(status)
