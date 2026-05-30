"""
產品 API 視圖
"""
from rest_framework import generics
from rest_framework.permissions import AllowAny
from .models import Product
from .serializers import ProductSerializer, ProductListSerializer


class ProductListView(generics.ListAPIView):
    """取得所有上架商品列表（依建立時間升冪，確保原始商品永遠排第一）"""
    permission_classes = [AllowAny]
    serializer_class = ProductListSerializer
    queryset = Product.objects.filter(is_active=True).order_by('created_at')


class ProductDetailView(generics.RetrieveAPIView):
    """取得單一商品詳細資料（含功能特點與規格）"""
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer
    queryset = Product.objects.filter(is_active=True)
