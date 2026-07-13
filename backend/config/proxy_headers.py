from django.conf import settings

from config.client_ip import is_trusted_proxy_address


class TrustedProxyHeadersMiddleware:
    """只讓可信直連代理提供 HTTPS scheme 標頭。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        remote_address = request.META.get("REMOTE_ADDR", "")
        if not settings.TRUST_PROXY_SSL_HEADER or not is_trusted_proxy_address(
            remote_address
        ):
            request.META.pop("HTTP_X_FORWARDED_PROTO", None)
        return self.get_response(request)
