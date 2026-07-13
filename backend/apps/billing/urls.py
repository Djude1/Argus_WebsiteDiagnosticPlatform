from django.urls import path

from apps.billing.views import (
    PurchaseView,
    ecpay_callback,
    list_plans,
    my_orders,
    my_wallet,
)

urlpatterns = [
    path("wallet/", my_wallet, name="billing-wallet"),
    path("plans/", list_plans, name="billing-plans"),
    path("purchase/", PurchaseView.as_view(), name="billing-purchase"),
    path("ecpay/callback/", ecpay_callback, name="billing-ecpay-callback"),
    path("orders/", my_orders, name="billing-orders"),
]
