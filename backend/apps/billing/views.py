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
    build_checkout_fields,
    merchant_trade_no,
    verify_check_mac_value,
)
from apps.billing.emails import send_purchase_receipt
from apps.billing.models import PricingPlan, PurchaseOrder
from apps.billing.serializers import (
    CoinWalletSerializer,
    PricingPlanSerializer,
    PurchaseOrderSerializer,
    PurchaseRequestSerializer,
)
from apps.billing.services import complete_purchase_order, get_or_create_wallet


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def my_wallet(request):
    """取得目前使用者的錢包餘額、累計資料與最近 20 筆交易。"""
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
        "purchase_enabled": settings.ARGUS_PAYMENT_MODE == "ecpay_test",
    })


class PurchaseView(views.APIView):
    """建立 pending 訂單並回傳綠界測試環境的簽章表單。"""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        if settings.ARGUS_PAYMENT_MODE != "ecpay_test":
            return Response(
                {"detail": "綠界測試付款目前未啟用；不會建立訂單或直接入點。"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
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
            note="等待綠界測試環境付款通知",
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
    """驗證綠界付款通知並冪等入點；回應必須是純文字 1|OK。"""
    payload = {str(key): str(value) for key, value in request.data.items()}
    if settings.ARGUS_PAYMENT_MODE != "ecpay_test" or not verify_check_mac_value(payload):
        return HttpResponse("0|ERROR", status=400, content_type="text/plain")
    if payload.get("MerchantID") != settings.ECPAY_MERCHANT_ID:
        return HttpResponse("0|ERROR", status=400, content_type="text/plain")
    try:
        order_id = int(payload.get("CustomField1", ""))
        order = PurchaseOrder.objects.select_related("plan", "user").get(pk=order_id)
        trade_amount = int(payload.get("TradeAmt", ""))
    except (TypeError, ValueError, PurchaseOrder.DoesNotExist):
        return HttpResponse("0|ERROR", status=400, content_type="text/plain")
    if (
        payload.get("MerchantTradeNo") != merchant_trade_no(order.id)
        or trade_amount != order.price_ntd
    ):
        return HttpResponse("0|ERROR", status=400, content_type="text/plain")
    # 綠界後台「模擬付款」只測 ReturnURL，不代表消費者完成付款，官方要求不可出貨/入點。
    if payload.get("SimulatePaid") == "1":
        return HttpResponse("1|OK", content_type="text/plain")
    if payload.get("RtnCode") != "1":
        if order.status == PurchaseOrder.Status.PENDING:
            order.note = f"綠界測試付款未完成：{payload.get('RtnCode', '')}"[:255]
            order.save(update_fields=["note"])
        return HttpResponse("1|OK", content_type="text/plain")
    try:
        order, completed = complete_purchase_order(
            order.id,
            provider_trade_no=payload.get("TradeNo", ""),
        )
    except ValueError:
        return HttpResponse("0|ERROR", status=409, content_type="text/plain")
    if completed:
        wallet = get_or_create_wallet(order.user)
        send_purchase_receipt(order, wallet.balance)
    return HttpResponse("1|OK", content_type="text/plain")

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
