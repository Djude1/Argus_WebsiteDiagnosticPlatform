"""
綠界 ECPay 付款工具
- 產生 CheckMacValue（SHA256）
- 建立付款表單參數
- 驗證回傳簽章

測試商店憑證（官方公開）：
  MerchantID : 2000132
  HashKey    : 5294y06JbISpM5x9
  HashIV     : v77hoKGq4kWxNNIS

上線前請在 .env 設定 ECPAY_MERCHANT_ID / ECPAY_HASH_KEY / ECPAY_HASH_IV
並將 ECPAY_USE_STAGE=False
"""
import hashlib
import urllib.parse
from datetime import datetime
import os


# ── 設定 ─────────────────────────────────────────────────────────────────────
MERCHANT_ID = os.getenv('ECPAY_MERCHANT_ID', '2000132')
HASH_KEY    = os.getenv('ECPAY_HASH_KEY',    '5294y06JbISpM5x9')
HASH_IV     = os.getenv('ECPAY_HASH_IV',     'v77hoKGq4kWxNNIS')
USE_STAGE   = os.getenv('ECPAY_USE_STAGE', 'true').lower() != 'false'

PAYMENT_URL = (
    'https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5'
    if USE_STAGE else
    'https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5'
)


def _check_mac(params: dict) -> str:
    """
    依照綠界規範計算 CheckMacValue
    步驟：
      1. 將所有參數（不含 CheckMacValue）依 key 字母排序
      2. 拼成 k=v&k=v 格式，頭加 HashKey、尾加 HashIV
      3. URL encode（空格 → +，特殊字元 %XX 大寫）
      4. 全部轉小寫後 SHA256，再全部轉大寫
    """
    # 排除 CheckMacValue 自身
    sorted_keys = sorted(k for k in params if k != 'CheckMacValue')
    raw = '&'.join(f'{k}={params[k]}' for k in sorted_keys)
    raw = f'HashKey={HASH_KEY}&{raw}&HashIV={HASH_IV}'

    # URL encode（遵循 .NET HttpUtility.UrlEncode 格式）
    encoded = urllib.parse.quote_plus(raw).lower()

    return hashlib.sha256(encoded.encode('utf-8')).hexdigest().upper()


def build_payment_params(order, return_url: str, client_back_url: str) -> dict:
    """
    建立傳給綠界的付款參數字典（不含 action URL）

    Args:
        order: Order model instance
        return_url: 後端 webhook（付款結果通知），需公開可存取
        client_back_url: 使用者付款後前端頁面（可為 localhost）
    Returns:
        dict，前端用來建立 form POST 至 PAYMENT_URL
    """
    # 綠界要求 MerchantTradeNo 不超過 20 字元，且每次唯一
    trade_no = f'ORD{order.order_number[-8:]}'[:20]

    # 商品名稱（綠界限制 400 bytes，不允許特殊符號）
    items = list(order.items.select_related('product').all())
    if items:
        item_name = '#'.join(
            f'{it.product.name} x{it.quantity}' for it in items
        )[:400]
    else:
        item_name = '商品'

    # 金額（整數，單位台幣）
    total = int(order.total_price)
    if total <= 0:
        total = 1   # 綠界最小金額 1 元

    now = datetime.now().strftime('%Y/%m/%d %H:%M:%S')

    params = {
        'MerchantID':        MERCHANT_ID,
        'MerchantTradeNo':   trade_no,
        'MerchantTradeDate': now,
        'PaymentType':       'aio',
        'TotalAmount':       str(total),
        'TradeDesc':         urllib.parse.quote('AI智慧眼鏡訂購', safe=''),
        'ItemName':          item_name,
        'ReturnURL':         return_url,
        'ClientBackURL':     client_back_url,
        'OrderResultURL':    client_back_url,
        'ChoosePayment':     'Credit',
        'EncryptType':       '1',
    }

    params['CheckMacValue'] = _check_mac(params)
    return params


def verify_callback(data: dict) -> bool:
    """
    驗證綠界回傳的 CheckMacValue 是否合法
    """
    received = data.get('CheckMacValue', '')
    expected = _check_mac(data)
    return received.upper() == expected.upper()


def is_payment_success(data: dict) -> bool:
    """
    判斷付款是否成功：RtnCode == '1'
    """
    return str(data.get('RtnCode', '')) == '1'
