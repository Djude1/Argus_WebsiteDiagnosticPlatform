"""
訂單 URL 路由
"""
from django.urls import path
from .views import OrderCreateView

urlpatterns = [
    path('', OrderCreateView.as_view(), name='order-create'),
]
