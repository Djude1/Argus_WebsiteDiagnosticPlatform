"""
訂單 URL 路由
"""
from django.urls import path
from .views import OrderCreateView, PaymentCreateView, PaymentCallbackView, PaymentResultView

urlpatterns = [
    path('',                               OrderCreateView.as_view(),    name='order-create'),
    path('<int:order_id>/payment/',        PaymentCreateView.as_view(),  name='payment-create'),
    path('payment-callback/',              PaymentCallbackView.as_view(),name='payment-callback'),
    path('<int:order_id>/payment-status/', PaymentResultView.as_view(),  name='payment-status'),
]
