from django.conf import settings


def playwright_launch_kwargs() -> dict:
    """讓 Chromium 明確走受控 egress proxy；空設定維持本機直連。"""
    if not settings.ARGUS_EGRESS_PROXY_URL:
        return {}
    return {"proxy": {"server": settings.ARGUS_EGRESS_PROXY_URL}}
