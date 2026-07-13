"""綠界全方位金流測試環境的簽章與結帳參數。"""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

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


def merchant_trade_no(order_id: int) -> str:
    """以資料庫訂單 ID 產生唯一且不超過綠界 20 字元限制的編號。"""
    if order_id < 1 or order_id > 999_999_999_999_999:
        raise ValueError("訂單 ID 超出綠界 MerchantTradeNo 可表示範圍")
    return f"ARGUS{order_id:015d}"


def _client_back_url(order_id: int) -> str:
    parsed = urlsplit(settings.ECPAY_CLIENT_BACK_URL)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({"payment_return": "1", "order_id": str(order_id)})
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


def build_checkout_fields(order) -> dict[str, str]:
    fields = {
        "MerchantID": settings.ECPAY_MERCHANT_ID,
        "MerchantTradeNo": merchant_trade_no(order.id),
        "MerchantTradeDate": timezone.localtime().strftime("%Y/%m/%d %H:%M:%S"),
        "PaymentType": "aio",
        "TotalAmount": str(order.price_ntd),
        "TradeDesc": "Argus 點數測試訂單",
        "ItemName": f"{order.plan.name} {order.coin_amount} coin",
        "ReturnURL": settings.ECPAY_RETURN_URL,
        "ChoosePayment": "Credit",
        "EncryptType": "1",
        "ClientBackURL": _client_back_url(order.id),
        "NeedExtraPaidInfo": "N",
        "CustomField1": str(order.id),
    }
    fields["CheckMacValue"] = build_check_mac_value(
        fields,
        hash_key=settings.ECPAY_HASH_KEY,
        hash_iv=settings.ECPAY_HASH_IV,
    )
    return fields
