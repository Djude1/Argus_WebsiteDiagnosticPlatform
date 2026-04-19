"""
產品序列化器
"""

from rest_framework import serializers
from .models import Product, ProductFeature, ProductSpec


class ProductFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductFeature
        fields = ("id", "title", "description", "icon", "order")


class ProductSpecSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSpec
        fields = ("id", "key", "value", "order")


class ProductSerializer(serializers.ModelSerializer):
    features = ProductFeatureSerializer(many=True, read_only=True)
    specs = ProductSpecSerializer(many=True, read_only=True)
    discount_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "short_description",
            "description",
            "price",
            "original_price",
            "discount_percentage",
            "stock",
            "image",
            "model_3d",
            "camera_height",
            "is_active",
            "features",
            "specs",
            "created_at",
            "updated_at",
        )

    def get_discount_percentage(self, obj):
        """計算折扣百分比"""
        if obj.original_price and obj.original_price > obj.price:
            discount = (1 - obj.price / obj.original_price) * 100
            return round(discount)
        return 0


class ProductListSerializer(serializers.ModelSerializer):
    """列表用精簡版序列化器"""

    discount_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "short_description",
            "price",
            "original_price",
            "discount_percentage",
            "stock",
            "image",
            "is_active",
        )

    def get_discount_percentage(self, obj):
        if obj.original_price and obj.original_price > obj.price:
            return round((1 - obj.price / obj.original_price) * 100)
        return 0
