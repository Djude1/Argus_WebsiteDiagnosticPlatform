from django.urls import path

from apps.accounts.views import (
    ChangePasswordView,
    CookieTokenRefreshView,
    EmailLoginView,
    EmailRegisterView,
    GoogleLoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
)

urlpatterns = [
    path("google/", GoogleLoginView.as_view(), name="google-login"),
    path("register/", EmailRegisterView.as_view(), name="email-register"),
    path("email-login/", EmailLoginView.as_view(), name="email-login"),
    path("refresh/", CookieTokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
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
