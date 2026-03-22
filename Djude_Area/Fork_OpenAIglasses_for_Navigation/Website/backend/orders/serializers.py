"""
訂單序列化器
"""
from rest_framework import serializers
from django.db import transaction
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
        for item in validated_data['items']:
            product = Product.objects.get(pk=item['product_id'])
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
            product.stock -= quantity
            product.save(update_fields=['stock'])

        return order


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            'id', 'order_number', 'customer_name', 'customer_email',
            'customer_phone', 'shipping_address', 'total_price',
            'status', 'notes', 'items', 'created_at'
        )
