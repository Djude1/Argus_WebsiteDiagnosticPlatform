from rest_framework.throttling import (
    AnonRateThrottle as DRFAnonRateThrottle,
)
from rest_framework.throttling import (
    ScopedRateThrottle as DRFScopedRateThrottle,
)
from rest_framework.throttling import (
    UserRateThrottle as DRFUserRateThrottle,
)

from config.client_ip import resolve_client_ip


class TrustedProxyIdentMixin:
    def get_ident(self, request):
        return resolve_client_ip(request)


class AnonRateThrottle(TrustedProxyIdentMixin, DRFAnonRateThrottle):
    pass


class UserRateThrottle(TrustedProxyIdentMixin, DRFUserRateThrottle):
    pass


class ScopedRateThrottle(TrustedProxyIdentMixin, DRFScopedRateThrottle):
    pass
