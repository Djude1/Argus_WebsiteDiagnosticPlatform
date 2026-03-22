"""
產品 URL 路由
"""
from django.urls import path
from .views import ProductListView, ProductDetailView

urlpatterns = [
    path('', ProductListView.as_view(), name='product-list'),
    path('<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
]
