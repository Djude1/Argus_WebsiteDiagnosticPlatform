from django.urls import path

from apps.accounts.views import (
    ChangePasswordView,
    EmailLoginView,
    EmailRegisterView,
    GoogleLoginView,
    MeView,
)

urlpatterns = [
    path("google/", GoogleLoginView.as_view(), name="google-login"),
    path("register/", EmailRegisterView.as_view(), name="email-register"),
    path("email-login/", EmailLoginView.as_view(), name="email-login"),
    path("me/", MeView.as_view(), name="me"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
]
