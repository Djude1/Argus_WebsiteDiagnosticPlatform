"""
訂單管理後台 API
"""
from rest_framework import generics, serializers as drf_serializers
from .models import Order, OrderItem
from accounts.permissions import IsStaff
from analytics.utils import log_activity


class AdminOrderItemSerializer(drf_serializers.ModelSerializer):
    product_name = drf_serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = ('id', 'product', 'product_name', 'quantity', 'price')


class AdminOrderSerializer(drf_serializers.ModelSerializer):
    items = AdminOrderItemSerializer(many=True, read_only=True)
    status_display = drf_serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Order
        fields = (
            'id', 'order_number', 'customer_name', 'customer_email',
            'customer_phone', 'shipping_address', 'total_price',
            'status', 'status_display', 'notes', 'items',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'order_number', 'customer_name', 'customer_email',
            'customer_phone', 'shipping_address', 'total_price',
            'items', 'created_at', 'updated_at',
        )


class AdminOrderListView(generics.ListAPIView):
    permission_classes = [IsStaff]
    serializer_class = AdminOrderSerializer

    def get_queryset(self):
        qs = Order.objects.all()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class AdminOrderDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsStaff]
    serializer_class = AdminOrderSerializer
    queryset = Order.objects.all()

    def perform_update(self, serializer):
        old_status = serializer.instance.status
        super().perform_update(serializer)
        new_status = serializer.instance.status
        if old_status != new_status:
            log_activity(self.request, 'update', '訂單',
                         serializer.instance.id,
                         f'{serializer.instance.order_number} ({old_status}→{new_status})')
