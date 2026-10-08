"""掃描背景執行的部署設定檢查。"""

import ipaddress

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


@register()
def check_scanner_egress_ips(app_configs, **kwargs):
    """公開頁列出的掃描出口 IP 必須是合法的 IP 或 CIDR，否則對方照著放行也沒用。"""
    invalid = []
    for item in getattr(settings, "ARGUS_SCANNER_EGRESS_IPS", []):
        try:
            ipaddress.ip_network(item, strict=False)
        except ValueError:
            invalid.append(item)
    if invalid:
        return [
            Error(
                f"ARGUS_SCANNER_EGRESS_IPS 有 {len(invalid)} 個不是 IP 或 CIDR 的項目。",
                hint="以逗號分隔，例如 203.0.113.10,198.51.100.0/28。",
                id="scans.E003",
            )
        ]
    return []
