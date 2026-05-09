"""
訂單 API 視圖
"""
import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order
from .serializers import OrderCreateSerializer, OrderSerializer
from . import ecpay as ecpay_util

logger = logging.getLogger(__name__)


class OrderCreateView(APIView):
    """建立新訂單（允許訪客購買）"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OrderCreateSerializer(
            data=request.data,
            context={'user': request.user if request.user.is_authenticated else None}
        )
        if serializer.is_valid():
            order = serializer.save()
            response_serializer = OrderSerializer(order)
            return Response(
                {
                    'message': '訂單建立成功！請繼續進行付款。',
                    'order': response_serializer.data
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PaymentCreateView(APIView):
    """
    為已建立的訂單產生綠界付款表單參數
    GET /api/orders/<order_id>/payment/
    回傳：{ payment_url, params }，前端用來自動提交表單
    """
    permission_classes = [AllowAny]

    def get(self, request, order_id):
        try:
            order = Order.objects.prefetch_related('items__product').get(pk=order_id)
        except Order.DoesNotExist:
            return Response({'error': '找不到此訂單'}, status=404)

        if order.payment_status == 'paid':
            return Response({'error': '此訂單已完成付款'}, status=400)

        scheme = 'https' if request.is_secure() else 'http'
        host   = request.get_host()
        base   = f'{scheme}://{host}'

        return_url      = f'{base}/api/orders/payment-callback/'
        client_back_url = f'{base}/purchase/result?order_id={order.id}'

        params = ecpay_util.build_payment_params(order, return_url, client_back_url)

        return Response({
            'payment_url': ecpay_util.PAYMENT_URL,
            'params':      params,
        })


class PaymentCallbackView(APIView):
    """
    綠界 ReturnURL webhook（POST，後台通知）
    回應必須是純文字 '1|OK' 才算接收成功
    """
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}

        if not ecpay_util.verify_callback(data):
            logger.warning('ECPay callback CheckMacValue 驗證失敗: %s', data)
            return Response('0|Error', content_type='text/plain')

        merchant_trade_no = data.get('MerchantTradeNo', '')
        suffix = merchant_trade_no[3:] if merchant_trade_no.startswith('ORD') else merchant_trade_no

        try:
            order = Order.objects.get(order_number__endswith=suffix)
        except Order.DoesNotExist:
            logger.warning('找不到訂單：MerchantTradeNo=%s', merchant_trade_no)
            return Response('0|Error', content_type='text/plain')
        except Order.MultipleObjectsReturned:
            logger.error('MerchantTradeNo=%s 對應到多筆訂單，請檢查資料', merchant_trade_no)
            return Response('0|Error', content_type='text/plain')

        # 幂等性：已付款的訂單不重複處理
        if order.payment_status == 'paid':
            logger.info('訂單 %s 已付款，忽略重複 callback', order.order_number)
            return Response('1|OK', content_type='text/plain')

        if ecpay_util.is_payment_success(data):
            order.payment_status = 'paid'
            order.ecpay_trade_no = data.get('TradeNo', '')
            order.paid_at        = timezone.now()
            order.status         = 'confirmed'
            order.save(update_fields=['payment_status', 'ecpay_trade_no', 'paid_at', 'status'])
            logger.info('訂單 %s 付款成功', order.order_number)
        else:
            order.payment_status = 'failed'
            order.save(update_fields=['payment_status'])
            logger.info('訂單 %s 付款失敗，RtnCode=%s', order.order_number, data.get('RtnCode'))

        return Response('1|OK', content_type='text/plain')


class PaymentResultView(APIView):
    """
    查詢訂單付款狀態（前端 /purchase/result 頁面用）
    GET /api/orders/<order_id>/payment-status/
    """
    permission_classes = [AllowAny]

    def get(self, request, order_id):
        try:
            order = Order.objects.prefetch_related('items__product').get(pk=order_id)
        except Order.DoesNotExist:
            return Response({'error': '找不到此訂單'}, status=404)

        serializer = OrderSerializer(order)
        return Response({
            'payment_status': order.payment_status,
            'order': serializer.data,
        })
