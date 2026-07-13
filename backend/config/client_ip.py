import ipaddress

from django.conf import settings


def _trusted_proxy_networks():
    networks = []
    for value in settings.TRUSTED_PROXY_CIDRS:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return networks


def is_trusted_proxy_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(address in network for network in _trusted_proxy_networks())


def resolve_client_ip(request) -> str:
    """只在直連來源為可信代理時，由右向左解析 forwarded chain。"""
    remote_value = request.META.get("REMOTE_ADDR", "0.0.0.0")
    try:
        remote = ipaddress.ip_address(remote_value)
    except ValueError:
        return "0.0.0.0"

    networks = _trusted_proxy_networks()
    if not is_trusted_proxy_address(remote_value):
        return str(remote)

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if not forwarded or len(forwarded) > 2048:
        return str(remote)
    values = [value.strip() for value in forwarded.split(",")]
    if not values or len(values) > 20 or any(not value for value in values):
        return str(remote)

    parsed_chain = []
    try:
        parsed_chain = [ipaddress.ip_address(value) for value in values]
    except ValueError:
        return str(remote)

    for candidate in reversed(parsed_chain):
        if not any(candidate in network for network in networks):
            return str(candidate)
    return str(remote)
