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
