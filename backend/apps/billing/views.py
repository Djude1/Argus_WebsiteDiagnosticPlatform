from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status, views
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.billing.models import PricingPlan, PurchaseOrder
from apps.billing.serializers import (
    CoinWalletSerializer,
    PricingPlanSerializer,
    PurchaseOrderSerializer,
    PurchaseRequestSerializer,
)
from apps.billing.emails import send_purchase_receipt
from apps.billing.services import get_or_create_wallet, purchase_plan


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
    return Response({"plans": PricingPlanSerializer(plans, many=True).data})


class PurchaseView(views.APIView):
    """3 步驟結帳的最後一哩。

    流程：建 PurchaseOrder(pending) → 呼叫 purchase_plan → 把入帳的 tx 連結到 order
    → status 轉為 paid → 回傳 wallet 與 order。
    """

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = PurchaseRequestSerializer(data=request.data, context={})
        serializer.is_valid(raise_exception=True)
        plan: PricingPlan = serializer.context["plan"]
        data = serializer.validated_data

        # 先建 pending order，做為「即使下游 coin 入帳失敗也有訂單紀錄」的依據
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
            note=f"3 步驟結帳：{data['buyer_name']}",
        )
        # 模擬付款：直接入帳；正式金流時這段會搬到 callback/webhook
        tx = purchase_plan(request.user, plan)
        order.transaction = tx
        order.status = PurchaseOrder.Status.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=["transaction", "status", "paid_at"])

        wallet = get_or_create_wallet(request.user)
        # 寄送購點收據（失敗不阻擋）
        send_purchase_receipt(order, wallet.balance)
        return Response(
            {
                "wallet": CoinWalletSerializer(wallet).data,
                "order": PurchaseOrderSerializer(order).data,
            },
            status=status.HTTP_201_CREATED,
        )

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
