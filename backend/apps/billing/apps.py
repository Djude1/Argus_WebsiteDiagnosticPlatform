from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing"
    label = "billing"

    def ready(self) -> None:
        # 啟動時註冊 signal：使用者建立時自動建立錢包與首月贈點
        from apps.billing import signals  # noqa: F401

