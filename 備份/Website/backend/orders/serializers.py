"""
訂單序列化器
"""
from rest_framework import serializers
from django.db import transaction
from django.db.models import F
from .models import Order, OrderItem
from products.models import Product


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = ('id', 'product', 'product_name', 'quantity', 'price')
        read_only_fields = ('price',)


class OrderItemInputSerializer(serializers.Serializer):
    """單筆訂購明細輸入"""
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=99)


class OrderCreateSerializer(serializers.Serializer):
    """建立訂單的輸入驗證（支援多商品）"""
    customer_name = serializers.CharField(max_length=100)
    customer_email = serializers.EmailField()
    customer_phone = serializers.CharField(max_length=20)
    shipping_address = serializers.CharField()
    items = OrderItemInputSerializer(many=True)
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError('至少需選擇一件商品')
        return value

    def validate(self, data):
        errors = []
        for item in data['items']:
            try:
                product = Product.objects.get(pk=item['product_id'], is_active=True)
            except Product.DoesNotExist:
                errors.append(f'商品 ID {item["product_id"]} 不存在或已下架')
                continue
            if product.stock < item['quantity']:
                errors.append(f'「{product.name}」庫存不足，目前庫存為 {product.stock} 件')
        if errors:
            raise serializers.ValidationError(errors)
        return data

    @transaction.atomic
    def create(self, validated_data):
        total_price = 0
        item_rows = []
        # select_for_update() 鎖定商品列，防止並發下單的庫存競爭條件
        for item in validated_data['items']:
            product = Product.objects.select_for_update().get(pk=item['product_id'])
            if product.stock < item['quantity']:
                raise serializers.ValidationError(
                    {'items': [f'「{product.name}」庫存不足，目前庫存為 {product.stock} 件']}
                )
            total_price += product.price * item['quantity']
            item_rows.append((product, item['quantity']))

        order = Order.objects.create(
            customer_name=validated_data['customer_name'],
            customer_email=validated_data['customer_email'],
            customer_phone=validated_data['customer_phone'],
            shipping_address=validated_data['shipping_address'],
            total_price=total_price,
            notes=validated_data.get('notes', ''),
            user=self.context.get('user')
        )
        for product, quantity in item_rows:
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                price=product.price
            )
            # 使用 F() 表達式進行資料庫層級原子扣庫，避免讀寫競爭
            Product.objects.filter(pk=product.pk).update(stock=F('stock') - quantity)

        return order


class OrderSerializer(serializers.ModelSerializer):
    items          = OrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Order
        fields = (
            'id', 'order_number', 'customer_name', 'customer_email',
            'customer_phone', 'shipping_address', 'total_price',
            'status', 'status_display', 'payment_status', 'notes', 'items', 'created_at'
        )
