"""掃描背景執行的部署設定檢查。"""

from django.conf import settings
from django.core.checks import Error, register


@register(deploy=True)
def check_eager_is_debug_only(app_configs, **kwargs):
    """正式環境不可讓 web process 以 eager 模式充當掃描 worker。"""
    if settings.CELERY_TASK_ALWAYS_EAGER and not settings.DEBUG:
        return [
            Error(
                "CELERY_TASK_ALWAYS_EAGER 只能用於 DEBUG 本機 smoke test；"
                "正式環境必須使用 broker 與 Celery worker。",
                id="scans.E001",
            )
        ]
    return []


@register(deploy=True)
def check_private_targets_is_debug_only(app_configs, **kwargs):
    """私網目標旁路只允許 DEBUG 本機／隔離 demo；正式環境維持公開目標政策。"""
    if getattr(settings, "ARGUS_ALLOW_PRIVATE_TARGETS", False) and not settings.DEBUG:
        return [
            Error(
                "ARGUS_ALLOW_PRIVATE_TARGETS 只能用於 DEBUG 本機／隔離 demo；"
                "正式環境必須維持公開 HTTP(S) 目標政策。",
                id="scans.E002",
            )
        ]
    return []
