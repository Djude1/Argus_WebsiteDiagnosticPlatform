import ipaddress
import socket
from urllib.parse import urlparse

from config.client_ip import resolve_client_ip

OBVIOUS_THIRD_PARTY_DOMAINS = {
    "google.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "x.com",
    "twitter.com",
    "amazon.com",
    "paypal.com",
}

BANK_KEYWORDS = {"bank", "銀行", "信用合作社"}
PUBLIC_WEB_PORTS = {80, 443}


class PublicScanTargetError(ValueError):
    """掃描目標不符合公開 HTTP(S) 位址政策。"""


def _parse_url(raw_url: str):
    parsed = urlparse(raw_url.strip())
    if not parsed.scheme:
        parsed = urlparse(f"https://{raw_url.strip()}")
    try:
        hostname = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise PublicScanTargetError("請輸入有效的 HTTP 或 HTTPS 網址。") from exc
    return parsed, hostname, port


def _host_for_url(hostname: str) -> str:
    return f"[{hostname}]" if ":" in hostname else hostname


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not ip.is_global


def _resolve_host_ips(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        records = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise PublicScanTargetError("無法解析此網域，請確認網址是否正確。") from exc

    ips: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for record in records:
        try:
            ips.add(ipaddress.ip_address(record[4][0]))
        except ValueError:
            continue
    if not ips:
        raise PublicScanTargetError("無法解析此網域，請確認網址是否正確。")
    return sorted(ips, key=lambda item: (item.version, int(item)))


def resolve_public_host_ips(hostname: str) -> list[str]:
    """解析並回傳可固定連線的公開 IP；任一非公開結果都拒絕。"""
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        ips = _resolve_host_ips(hostname)
    else:
        ips = [literal_ip]
    if any(_is_blocked_ip(ip) for ip in ips):
        raise PublicScanTargetError("掃描目標不允許內網、保留或非公開位址。")
    return [str(ip) for ip in ips]


def normalize_url(raw_url: str) -> str:
    parsed, hostname, port_value = _parse_url(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("請輸入有效的 HTTP 或 HTTPS 網址。")
    port = f":{port_value}" if port_value else ""
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme.lower()}://{_host_for_url(hostname)}{port}{path}{query}"


def assert_public_http_url(raw_url: str) -> str:
    """正規化 URL，並確認每一筆 DNS 結果都是公開位址。"""
    raw_parsed, _, _ = _parse_url(raw_url)
    if raw_parsed.username is not None or raw_parsed.password is not None:
        raise PublicScanTargetError("掃描網址不可包含帳號或密碼。")
    normalized = normalize_url(raw_url)
    parsed, hostname, port = _parse_url(normalized)
    if not hostname or hostname in {"localhost", "ip6-localhost"}:
        raise PublicScanTargetError("掃描目標不允許 localhost 或內網位址。")
    if port is not None and port not in PUBLIC_WEB_PORTS:
        raise PublicScanTargetError("掃描目標只允許標準 HTTP／HTTPS 連接埠。")

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        if "." not in hostname:
            raise PublicScanTargetError("請輸入完整且可解析的公開網域。") from None
        try:
            hostname.encode("idna")
        except UnicodeError as exc:
            raise PublicScanTargetError("請輸入有效的公開網域。") from exc
        resolve_public_host_ips(hostname)
    else:
        resolve_public_host_ips(str(literal_ip))
    return normalized


def assert_public_websocket_url(raw_url: str) -> str:
    """將 WebSocket URL 套用與 HTTP(S) 相同的公開位址政策。"""
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {"ws", "wss"}:
        raise PublicScanTargetError("只允許公開的 WebSocket 連線。")
    http_scheme = "https" if parsed.scheme == "wss" else "http"
    assert_public_http_url(parsed._replace(scheme=http_scheme).geturl())
    return raw_url


def get_origin(url: str) -> str:
    parsed, hostname, port_value = _parse_url(url)
    port = f":{port_value}" if port_value else ""
    return f"{parsed.scheme}://{_host_for_url(hostname)}{port}"


def get_hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def is_obvious_third_party(hostname: str) -> bool:
    if hostname in OBVIOUS_THIRD_PARTY_DOMAINS:
        return True
    if any(hostname.endswith(f".{domain}") for domain in OBVIOUS_THIRD_PARTY_DOMAINS):
        return True
    return any(keyword in hostname for keyword in BANK_KEYWORDS)


def get_client_ip(request) -> str:
    return resolve_client_ip(request)


def registrable_domain(url_or_origin: str) -> str:
    """從 URL 或 origin 抽出 hostname（小寫）。

    刻意簡化：不做 eTLD+1 萃取，完整 hostname 就是閘門比對單位；
    子網域涵蓋（www.example.com 對 example.com 驗證）由 user_owns_domain 處理。
    """
    return (urlparse((url_or_origin or "").strip()).hostname or "").lower().rstrip(".")


def user_owns_domain(user, hostname: str) -> bool:
    """該 user 是否對 hostname 持有有效的網域所有權驗證。

    比對規則：verified domain 等於 hostname 本身，或 hostname 是其子網域
    （hostname.endswith("." + domain)，例：www.example.com 對 example.com）。
    有效判定走 VerifiedDomain.is_effectively_verified（人工核准或已驗證未過期）。
    """
    if not user or not user.id or not hostname:
        return False
    # 延遲 import：models 反向 import 本模組（ScanJob.clean 用到），頂層互 import 會循環
    from apps.scans.models import VerifiedDomain

    hostname = hostname.lower().rstrip(".")
    candidates = (
        hostname,
        # 父網域候選：a.b.example.com → 依序嘗試 b.example.com / example.com，
        # 讓「對註冊域驗證一次、子網域全部涵蓋」不用精確知道 eTLD+1 邊界
        *{
            hostname.split(".", i)[-1]
            for i in range(1, hostname.count("."))
        },
    )
    domains = set(VerifiedDomain.objects.filter(user=user, domain__in=candidates))
    return any(
        vd.is_effectively_verified
        and (hostname == vd.domain or hostname.endswith(f".{vd.domain}"))
        for vd in domains
    )

