"""購點與訂閱端到端檢測（只對本機或 Stage 環境執行）。

流程：公開方案 → 註冊測試帳號 → 建立購點訂單並驗算綠界表單簽章 →
模擬綠界 ReturnURL 回呼（偽造簽章／竄改金額／模擬付款／付款失敗都不得入點，成功付款冪等入點）→
訂閱首月入點 → 取消訂閱。CheckMacValue 為獨立實作，不借用後端程式，才能交叉驗證。

用法（在專案根目錄，後端需以 ARGUS_PAYMENT_MODE=ecpay_test 啟動）：
    uv run python scripts/billing_e2e_check.py
環境變數：ARGUS_E2E_BASE（預設 http://127.0.0.1:8000/api），
ECPAY_MERCHANT_ID / ECPAY_HASH_KEY / ECPAY_HASH_IV（預設讀 .env，與後端同一組）。
會在目標環境建立一個 billing-e2e-*@example.com 測試帳號與一筆測試訂單；不要對正式環境執行。
"""
import hashlib, json, os, time, urllib.parse, urllib.request, http.cookiejar, sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass
BASE = os.getenv("ARGUS_E2E_BASE", "http://127.0.0.1:8000/api").rstrip("/")
KEY, IV, MID = os.getenv("ECPAY_HASH_KEY", ""), os.getenv("ECPAY_HASH_IV", ""), os.getenv("ECPAY_MERCHANT_ID", "")
if not (KEY and IV and MID):
    sys.exit("缺少 ECPAY_MERCHANT_ID / ECPAY_HASH_KEY / ECPAY_HASH_IV（請寫在 .env）")
jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
TOKEN = None
results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
def req(method, path, data=None, form=False, auth=True):
    url = BASE + path
    headers = {}
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode(); headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode(); headers["Content-Type"] = "application/json"
    if auth and TOKEN: headers["Authorization"] = f"Bearer {TOKEN}"
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = op.open(r); code = resp.status; raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        code = e.code; raw = e.read().decode()
    try: return code, json.loads(raw)
    except Exception: return code, raw
def mac(params):
    raw = "HashKey=%s&%s&HashIV=%s" % (KEY, "&".join(f"{k}={v}" for k, v in sorted(params.items()) if k != "CheckMacValue"), IV)
    enc = urllib.parse.quote_plus(raw, safe="-_.!*()").lower()
    return hashlib.sha256(enc.encode()).hexdigest().upper()

# 0. 官方文件測試向量
vec = dict(ChoosePayment='ALL',EncryptType='1',ItemName='Apple iphone 15',MerchantID='3002607',MerchantTradeDate='2023/03/12 15:30:23',MerchantTradeNo='ecpay20230312153023',PaymentType='aio',ReturnURL='https://www.ecpay.com.tw/receive.php',TotalAmount='30000',TradeDesc='促銷方案')
# 綠界官方文件的範例（使用綠界公開測試商店 3002607 的 HashKey/HashIV）
if MID == "3002607":
    check("CheckMacValue 與綠界官方文件範例一致", mac(vec) == "6C51C9E6888DE861FD62FB1DD17029FC742634498FD813DC43D4243B5685B840")

# 1. 公開方案
c, d = req("GET", "/billing/plans/", auth=False)
check("購點方案 API 開放（purchase_enabled）", c == 200 and d["purchase_enabled"] and d["payment_mode"] == "ecpay_test", f"{len(d['plans'])} 個方案")
plans = {p["code"]: p for p in d["plans"]}
c, d = req("GET", "/billing/subscription/plans/", auth=False)
check("訂閱方案 API 開放（subscribe_enabled）", c == 200 and d["subscribe_enabled"], ", ".join(f"{p['code']} NT${p['monthly_price_ntd']}/{p['monthly_coins']}coin" for p in d["plans"]))
subplans = d["plans"]

# 2. 註冊登入
email = f"billing-e2e-{int(time.time())}@example.com"
c, d = req("POST", "/auth/register/", {"email": email, "password": "Argus-E2E-pass-2026!"}, auth=False)
check("註冊測試帳號", c in (200, 201), str(c))
TOKEN = d.get("access") if isinstance(d, dict) else None
if not TOKEN:
    c, d = req("POST", "/auth/email-login/", {"email": email, "password": "Argus-E2E-pass-2026!"}, auth=False); TOKEN = d.get("access")
check("取得 access token", bool(TOKEN))
c, w = req("GET", "/billing/wallet/"); bal0 = w["balance"]
check("錢包可讀", c == 200, f"初始餘額 {bal0}")

# 3. 購點：建立 pending 訂單 + 綠界表單
plan = plans["standard"]
buyer = {"plan_code": plan["code"], "buyer_name": "測試買家", "buyer_email": email, "invoice_type": "personal", "carrier_type": "cloud", "agree_terms": True}
c, d = req("POST", "/billing/purchase/", buyer)
if c == 400: print("  purchase 400:", d)
check("建立購點訂單（201，狀態 pending）", c == 201 and d["order"]["status"] == "pending", f"order #{d.get('order',{}).get('id')}" if isinstance(d, dict) else str(d)[:200])
order = d["order"]; f = d["payment"]["fields"]
check("導向綠界 stage 結帳頁", d["payment"]["action"] == "https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5")
check("結帳表單簽章正確（獨立驗算 CheckMacValue）", mac(f) == f["CheckMacValue"])
check("表單金額／商店代號正確", f["TotalAmount"] == str(plan["price_ntd"]) and f["MerchantID"] == MID, f"NT${f['TotalAmount']}")
c, w = req("GET", "/billing/wallet/")
check("付款前不入點", w["balance"] == bal0)

def callback(**over):
    p = {"MerchantID": MID, "MerchantTradeNo": f["MerchantTradeNo"], "StoreID": "", "RtnCode": "1", "RtnMsg": "交易成功",
         "TradeNo": "2609272200000001", "TradeAmt": f["TotalAmount"], "PaymentDate": "2026/09/27 22:00:00", "PaymentType": "Credit_CreditCard",
         "PaymentTypeChargeFee": "10", "TradeDate": f["MerchantTradeDate"], "SimulatePaid": "0", "CustomField1": f["CustomField1"],
         "CustomField2": "", "CustomField3": "", "CustomField4": ""}
    p.update(over); sig = over.pop("_badmac", None)
    p.pop("_badmac", None); p["CheckMacValue"] = mac(p) if not sig else "0" * 64
    return req("POST", "/billing/ecpay/callback/", p, form=True, auth=False)

# 4. 異常回呼都不能入點
c, body = callback(_badmac=True); check("偽造簽章回呼被拒（400 0|ERROR）", c == 400 and "0|ERROR" in str(body))
c, body = callback(TradeAmt="1"); check("金額被竄改的回呼被拒", c == 400)
c, body = callback(SimulatePaid="1"); c2, w = req("GET", "/billing/wallet/")
check("綠界後台「模擬付款」回 1|OK 但不入點", c == 200 and "1|OK" in str(body) and w["balance"] == bal0)
c, body = callback(RtnCode="10100058", RtnMsg="付款失敗"); c2, w = req("GET", "/billing/wallet/")
check("付款失敗通知不入點", c == 200 and w["balance"] == bal0)

# 5. 成功付款回呼
c, body = callback(); c2, w = req("GET", "/billing/wallet/")
check("付款成功回呼 1|OK 並入點", c == 200 and "1|OK" in str(body) and w["balance"] == bal0 + plan["coin_amount"], f"{bal0} → {w['balance']}（+{plan['coin_amount']}）")
c, body = callback(); c2, w2 = req("GET", "/billing/wallet/")
check("重複回呼冪等（不重複入點）", c == 200 and w2["balance"] == w["balance"])
c, d = req("GET", "/billing/orders/")
o = next(x for x in d["orders"] if x["id"] == order["id"])
check("訂單狀態 → paid", o["status"] in ("paid", "completed"), o["status"])
bal1 = w2["balance"]

# 6. 訂閱
sp = subplans[0]
c, d = req("POST", "/billing/subscription/subscribe/", {"plan_code": sp["code"]})
check("訂閱成功（201）", c == 201, str(d)[:160] if c != 201 else sp["code"])
c, w = req("GET", "/billing/wallet/")
check("訂閱首月點數入帳", w["balance"] == bal1 + sp["monthly_coins"], f"{bal1} → {w['balance']}（+{sp['monthly_coins']}）")
c, d = req("GET", "/billing/subscription/")
check("訂閱狀態 active", c == 200 and d["subscription"] and d["subscription"]["status"] == "active", d["subscription"] and d["subscription"]["status"])
c, w2 = req("GET", "/billing/wallet/"); check("重新整理不重複發點（lazy 結算冪等）", w2["balance"] == w["balance"])
c, d = req("POST", "/billing/subscription/cancel/")
check("取消訂閱（權益保留到期滿）", c == 200 and d["subscription"]["status"] == "cancelled")
c, d = req("POST", "/billing/subscription/cancel/"); check("重複取消冪等", c == 200)
print("\n%d/%d 通過" % (sum(r[1] for r in results), len(results)))
sys.exit(0 if all(r[1] for r in results) else 1)
