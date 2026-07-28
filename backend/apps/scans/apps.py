from django.apps import AppConfig


class ScansConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.scans"
    label = "scans"

    def ready(self):
        from apps.scans import checks  # noqa: F401

