from django.urls import path

from apps.billing.views import (
    PurchaseView,
    cancel_my_subscription,
    ecpay_callback,
    list_plans,
    my_orders,
    my_subscription,
    my_wallet,
    subscribe,
    subscription_plans,
)

urlpatterns = [
    path("wallet/", my_wallet, name="billing-wallet"),
    path("plans/", list_plans, name="billing-plans"),
    path("purchase/", PurchaseView.as_view(), name="billing-purchase"),
    path("ecpay/callback/", ecpay_callback, name="billing-ecpay-callback"),
    path("orders/", my_orders, name="billing-orders"),
    path("subscription/plans/", subscription_plans, name="billing-subscription-plans"),
    path("subscription/", my_subscription, name="billing-subscription"),
    path("subscription/subscribe/", subscribe, name="billing-subscribe"),
    path("subscription/cancel/", cancel_my_subscription, name="billing-subscription-cancel"),
]
