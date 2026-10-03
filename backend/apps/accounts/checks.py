"""帳號相關的部署設定檢查。"""

from django.conf import settings
from django.core.checks import Error, Warning, register

LOCAL_HOSTNAMES = {"localhost", "127.0.0.1"}


@register()
def check_turnstile_settings(app_configs, **kwargs):
    """Turnstile 設定檢查；一般 `manage.py check` 就會跑（migrate Job／initContainer 都有執行）。

    只設一半是警告不是錯誤：ConfigMap 先放公開的 site key、維運再補 Secret 時，
    中間這段不該讓部署失敗，但 log 要看得到「人機驗證沒有啟用」。
    啟用了卻會讓所有驗證失敗（hostname 清單空、正式環境含 localhost）則直接擋下。
    """
    site_key = settings.TURNSTILE_SITE_KEY
    secret = settings.TURNSTILE_SECRET
    hostnames = set(settings.TURNSTILE_HOSTNAMES)
    errors = []
    if bool(site_key) != bool(secret):
        errors.append(
            Warning(
                "TURNSTILE_SITE_KEY 與 TURNSTILE_SECRET 只設定了一個，人機驗證目前沒有啟用。",
                hint="兩者都設定才會啟用；正式環境把 TURNSTILE_SECRET 放進 argus-secret。",
                id="accounts.W001",
            )
        )
    if site_key and secret and not hostnames:
        errors.append(
            Error(
                "已啟用 Turnstile 但 TURNSTILE_HOSTNAMES 為空，所有驗證都會失敗。",
                id="accounts.E002",
            )
        )
    if not settings.DEBUG and hostnames & LOCAL_HOSTNAMES:
        errors.append(
            Error(
                "正式環境的 TURNSTILE_HOSTNAMES 不可包含 localhost 或 127.0.0.1。",
                id="accounts.E003",
            )
        )
    return errors
