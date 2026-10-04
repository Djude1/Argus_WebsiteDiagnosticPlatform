from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, status, views
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from apps.billing.ecpay import (
    SUBSCRIPTION_EXEC_TIMES as ECPAY_SUBSCRIPTION_EXEC_TIMES,
)
from apps.billing.ecpay import (
    EcpayActionError,
    build_checkout_fields,
    build_subscription_checkout_fields,
    parse_trade_no,
    verify_check_mac_value,
)
from apps.billing.emails import send_purchase_receipt
from apps.billing.models import (
    PricingPlan,
    PurchaseOrder,
    SubscriptionOrder,
    SubscriptionPlan,
    UserSubscription,
)
from apps.billing.serializers import (
    CoinWalletSerializer,
    PricingPlanSerializer,
    PurchaseOrderSerializer,
    PurchaseRequestSerializer,
    SubscribeRequestSerializer,
    SubscriptionOrderSerializer,
    SubscriptionPlanSerializer,
    UserSubscriptionSerializer,
)
from apps.billing.services import (
    activate_subscription_order,
    cancel_subscription_and_recurring,
    complete_purchase_order,
    get_or_create_wallet,
    has_active_recurring,
    record_subscription_failure,
    record_subscription_period_charge,
    settle_subscription_safe,
)

_PAUSED_DETAIL = "線上付款目前未啟用；不會建立訂單或直接入點。"


def _ecpay_reply(ok: bool = True, status_code: int = 200) -> HttpResponse:
    """綠界通知的回覆必須是純文字 1|OK（失敗回 0|ERROR 讓綠界重送）。"""
    if ok:
        return HttpResponse("1|OK", content_type="text/plain")
    return HttpResponse("0|ERROR", status=status_code, content_type="text/plain")


def _verified_payload(request) -> dict[str, str] | None:
    """付款已啟用、CheckMacValue 與 MerchantID 都正確才回傳通知內容。"""
    payload = {str(key): str(value) for key, value in request.data.items()}
    if not settings.ARGUS_PAYMENT_ENABLED or not verify_check_mac_value(payload):
        return None
    if payload.get("MerchantID") != settings.ECPAY_MERCHANT_ID:
        return None
    return payload


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def my_wallet(request):
    """取得目前使用者的錢包餘額、累計資料與最近 20 筆交易。"""
    # 訂閱 lazy 結算：進場時先把到期未發的訂閱月贈點補上，餘額才是最新
    settle_subscription_safe(request.user)
    wallet = get_or_create_wallet(request.user)
    return Response(CoinWalletSerializer(wallet).data)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def list_plans(request):
    """列出所有啟用中的購點方案。"""
    plans = PricingPlan.objects.filter(is_active=True).order_by("sort_order", "price_ntd")
    return Response({
        "plans": PricingPlanSerializer(plans, many=True).data,
        "payment_mode": settings.ARGUS_PAYMENT_MODE,
        "purchase_enabled": settings.ARGUS_PAYMENT_ENABLED,
    })


class PurchaseView(views.APIView):
    """建立 pending 訂單並回傳綠界結帳的簽章表單（測試或正式環境依 ARGUS_PAYMENT_MODE）。"""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        if not settings.ARGUS_PAYMENT_ENABLED:
            return Response({"detail": _PAUSED_DETAIL}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        serializer = PurchaseRequestSerializer(data=request.data, context={})
        serializer.is_valid(raise_exception=True)
        plan: PricingPlan = serializer.context["plan"]
        data = serializer.validated_data

        order = PurchaseOrder.objects.create(
            user=request.user,
            plan=plan,
            price_ntd=plan.price_ntd,
            coin_amount=plan.coin_amount,
            buyer_name=data["buyer_name"],
            buyer_email=data["buyer_email"],
            invoice_type=data["invoice_type"],
            company_name=data.get("company_name", ""),
            tax_id=data.get("tax_id", ""),
            carrier_type=data.get("carrier_type", PurchaseOrder.CarrierType.CLOUD),
            carrier_id=data.get("carrier_id", ""),
            status=PurchaseOrder.Status.PENDING,
            note="等待綠界付款通知",
        )
        return Response(
            {
                "order": PurchaseOrderSerializer(order).data,
                "payment": {
                    "action": settings.ECPAY_CHECKOUT_URL,
                    "fields": build_checkout_fields(order),
                },
            },
            status=status.HTTP_201_CREATED,
        )


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def ecpay_callback(request):
    """綠界 ReturnURL：購點付款與訂閱首期授權的結果通知，驗證後冪等處理；回應必須是 1|OK。"""
    payload = _verified_payload(request)
    if payload is None:
        return _ecpay_reply(False, 400)
    parsed = parse_trade_no(payload.get("MerchantTradeNo", ""))
    try:
        trade_amount = int(payload.get("TradeAmt", ""))
    except ValueError:
        return _ecpay_reply(False, 400)
    if parsed is None:
        return _ecpay_reply(False, 400)
    kind, order_id = parsed
    if kind == "subscription":
        return _subscription_first_charge(payload, order_id, trade_amount)
    try:
        order = PurchaseOrder.objects.select_related("plan", "user").get(pk=order_id)
    except PurchaseOrder.DoesNotExist:
        return _ecpay_reply(False, 400)
    if trade_amount != order.price_ntd:
        return _ecpay_reply(False, 400)
    # 綠界後台「模擬付款」只測 ReturnURL，不代表消費者完成付款，官方要求不可出貨/入點。
    if payload.get("SimulatePaid") == "1":
        return _ecpay_reply()
    if payload.get("RtnCode") != "1":
        if order.status == PurchaseOrder.Status.PENDING:
            order.note = f"綠界付款未完成：{payload.get('RtnCode', '')}"[:255]
            order.save(update_fields=["note"])
        return _ecpay_reply()
    try:
        order, completed = complete_purchase_order(
            order.id,
            provider_trade_no=payload.get("TradeNo", ""),
        )
    except ValueError:
        return _ecpay_reply(False, 409)
    if completed:
        wallet = get_or_create_wallet(order.user)
        send_purchase_receipt(order, wallet.balance)
    return _ecpay_reply()


def _subscription_first_charge(payload: dict[str, str], order_id: int, amount: int) -> HttpResponse:
    try:
        order = SubscriptionOrder.objects.get(pk=order_id)
    except SubscriptionOrder.DoesNotExist:
        return _ecpay_reply(False, 400)
    if amount != order.price_ntd:
        return _ecpay_reply(False, 400)
    if payload.get("SimulatePaid") == "1":
        return _ecpay_reply()
    if payload.get("RtnCode") != "1":
        record_subscription_failure(
            order.id, rtn_code=payload.get("RtnCode", ""),
            rtn_msg=payload.get("RtnMsg", ""), amount=amount,
        )
        return _ecpay_reply()
    try:
        activate_subscription_order(
            order.id, provider_trade_no=payload.get("TradeNo", ""), amount=amount,
            rtn_msg=payload.get("RtnMsg", ""),
        )
    except ValueError:
        return _ecpay_reply(False, 409)
    return _ecpay_reply()


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def ecpay_period_callback(request):
    """綠界 PeriodReturnURL：訂閱第 2 期起每月扣款結果；成功才加一期並發點。"""
    payload = _verified_payload(request)
    if payload is None:
        return _ecpay_reply(False, 400)
    parsed = parse_trade_no(payload.get("MerchantTradeNo", ""))
    if parsed is None or parsed[0] != "subscription":
        return _ecpay_reply(False, 400)
    try:
        order = SubscriptionOrder.objects.get(pk=parsed[1])
        amount = int(payload.get("Amount", ""))
        total_success_times = int(payload.get("TotalSuccessTimes", ""))
    except (SubscriptionOrder.DoesNotExist, ValueError):
        return _ecpay_reply(False, 400)
    if amount != order.price_ntd:
        return _ecpay_reply(False, 400)
    if payload.get("SimulatePaid") == "1":
        return _ecpay_reply()
    if payload.get("RtnCode") != "1":
        record_subscription_failure(
            order.id, rtn_code=payload.get("RtnCode", ""),
            rtn_msg=payload.get("RtnMsg", ""), amount=amount,
        )
        return _ecpay_reply()
    record_subscription_period_charge(
        order.id,
        total_success_times=total_success_times,
        amount=amount,
        gwsr=payload.get("gwsr", ""),
        process_date=payload.get("ProcessDate", ""),
        rtn_msg=payload.get("RtnMsg", ""),
    )
    return _ecpay_reply()


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def my_orders(request):
    """我的訂購紀錄（最新 50 筆）。"""
    qs = (
        PurchaseOrder.objects.filter(user=request.user)
        .select_related("plan")
        .order_by("-created_at")[:50]
    )
    return Response({"orders": PurchaseOrderSerializer(qs, many=True).data})


# ---------- 輕量訂閱（無週期扣款；lazy 結算） ----------


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def subscription_plans(request):
    """列出所有啟用中的訂閱方案（公開，供前端定價頁顯示）。"""
    plans = (
        SubscriptionPlan.objects.filter(is_active=True)
        .order_by("sort_order", "monthly_price_ntd")
    )
    return Response({
        "plans": SubscriptionPlanSerializer(plans, many=True).data,
        "payment_mode": settings.ARGUS_PAYMENT_MODE,
        "subscribe_enabled": settings.ARGUS_PAYMENT_ENABLED,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def my_subscription(request):
    """自己的訂閱狀態；無訂閱時 subscription 欄位回 null。"""
    settle_subscription_safe(request.user)
    sub = UserSubscription.objects.select_related("plan").filter(
        user=request.user,
    ).first()
    return Response({
        "subscription": UserSubscriptionSerializer(sub).data if sub else None,
    })


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def subscribe(request):
    """訂閱方案：建立綠界信用卡定期定額委託，回傳結帳表單（每月自動扣款）。

    首期授權成功的通知（ReturnURL）才開通訂閱並發點；這裡不入點。
    已有自動續訂中的訂閱時回 409（避免重複扣款），要換方案請先取消。
    """
    if not settings.ARGUS_PAYMENT_ENABLED:
        return Response({"detail": _PAUSED_DETAIL}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    serializer = SubscribeRequestSerializer(data=request.data, context={})
    serializer.is_valid(raise_exception=True)
    plan = serializer.context["plan"]
    data = serializer.validated_data
    if has_active_recurring(request.user):
        return Response(
            {"detail": "你已有每月自動扣款中的訂閱；要換方案請先取消目前的訂閱。"},
            status=status.HTTP_409_CONFLICT,
        )
    order = SubscriptionOrder.objects.create(
        user=request.user,
        plan=plan,
        price_ntd=plan.monthly_price_ntd,
        monthly_coins=plan.monthly_coins,
        exec_times=ECPAY_SUBSCRIPTION_EXEC_TIMES,
        buyer_name=data["buyer_name"],
        buyer_email=data["buyer_email"],
        invoice_type=data["invoice_type"],
        company_name=data.get("company_name", ""),
        tax_id=data.get("tax_id", ""),
        carrier_type=data.get("carrier_type", PurchaseOrder.CarrierType.CLOUD),
        carrier_id=data.get("carrier_id", ""),
        payment_mode=settings.ARGUS_PAYMENT_MODE,
    )
    return Response(
        {
            "order": SubscriptionOrderSerializer(order).data,
            "payment": {
                "action": settings.ECPAY_CHECKOUT_URL,
                "fields": build_subscription_checkout_fields(order),
            },
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def cancel_my_subscription(request):
    """取消自己的訂閱：先請綠界停止每月扣款，成功後才取消（當期權益保留到期滿）。"""
    settle_subscription_safe(request.user)
    try:
        sub = cancel_subscription_and_recurring(request.user)
    except EcpayActionError as exc:
        return Response(
            {"detail": f"無法取消每月扣款：{exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    if sub is None:
        return Response(
            {"detail": "目前沒有可取消的訂閱。"},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response({"subscription": UserSubscriptionSerializer(sub).data})
