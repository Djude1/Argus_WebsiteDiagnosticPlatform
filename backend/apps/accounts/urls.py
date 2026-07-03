from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import (
    ChangePasswordView,
    EmailLoginView,
    EmailRegisterView,
    GoogleLoginView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
)

urlpatterns = [
    path("google/", GoogleLoginView.as_view(), name="google-login"),
    path("register/", EmailRegisterView.as_view(), name="email-register"),
    path("email-login/", EmailLoginView.as_view(), name="email-login"),
    # Refresh：以既有 refresh token 換發新 access（+ 新 refresh，舊 refresh 進 blacklist）
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path(
        "password-reset/request/",
        PasswordResetRequestView.as_view(),
        name="password-reset-request",
    ),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
]
