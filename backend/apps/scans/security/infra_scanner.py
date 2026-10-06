"""網站基礎架構辨識：網域 → IP → 反解（rDNS），以及是否位於 CDN／WAF／反向代理之後。

掃描器連到的不一定是網站真正的主機（Origin）。網站放在 Cloudflare 等服務後面時，
Port、伺服器與 TLS 等主機層級資訊反映的是邊緣節點，報告必須講清楚。

只查目標自身網域的 DNS（A／AAAA／CNAME／NS）與這些 IP 的 PTR，並讀爬蟲已取得的
回應標頭；不對目標發出額外 HTTP 請求。任何錯誤都只讓該欄位留空，不讓掃描失敗。
"""

from __future__ import annotations

import ipaddress

import dns.resolver
import dns.reversename

_TIMEOUT = 2.0
_LIFETIME = 3.0
MAX_ADDRESSES = 6

# Cloudflare 公告的邊緣網段（https://www.cloudflare.com/ips/，2026-10 版）
_CLOUDFLARE_NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in (
        "173.245.48.0/20",
        "103.21.244.0/22",
        "103.22.200.0/22",
        "103.31.4.0/22",
        "141.101.64.0/18",
        "108.162.192.0/18",
        "190.93.240.0/20",
        "188.114.96.0/20",
        "197.234.240.0/22",
        "198.41.128.0/17",
        "162.158.0.0/15",
        "104.16.0.0/13",
        "104.24.0.0/14",
        "172.64.0.0/13",
        "131.0.72.0/22",
        "2400:cb00::/32",
        "2606:4700::/32",
        "2803:f800::/32",
        "2405:b500::/32",
        "2405:8100::/32",
        "2a06:98c0::/29",
        "2c0f:f248::/32",
    )
)

# (服務名稱, 判斷依據) — 回應標頭特徵
_HEADER_SIGNATURES = (
    ("Cloudflare", lambda h: "cf-ray" in h or h.get("server", "").lower() == "cloudflare"),
    ("Amazon CloudFront", lambda h: "x-amz-cf-id" in h or "cloudfront" in h.get("via", "").lower()),
    (
        "Akamai",
        lambda h: "akamaighost" in h.get("server", "").lower() or "x-akamai-transformed" in h,
    ),
    (
        "Fastly",
        lambda h: "x-fastly-request-id" in h or "fastly" in h.get("x-served-by", "").lower(),
    ),
    ("Vercel", lambda h: "x-vercel-id" in h),
    ("Netlify", lambda h: "x-nf-request-id" in h),
    ("Sucuri", lambda h: "x-sucuri-id" in h),
    ("Imperva", lambda h: "x-iinfo" in h or "incap_ses" in h.get("set-cookie", "").lower()),
    ("Azure Front Door", lambda h: "x-azure-ref" in h),
)

# CNAME／反解主機名稱的後綴
_HOSTNAME_SUFFIXES = (
    ("Amazon CloudFront", ("cloudfront.net",)),
    ("Akamai", ("akamaiedge.net", "edgekey.net", "edgesuite.net", "akamaitechnologies.com")),
    ("Fastly", ("fastly.net", "fastlylb.net")),
    ("Vercel", ("vercel-dns.com",)),
    ("Netlify", ("netlify.app", "netlify.com")),
    ("Azure Front Door", ("azurefd.net", "azureedge.net")),
    ("Cloudflare", ("cdn.cloudflare.net",)),
)

# 這些服務同時提供 WAF；只代表「具備」能力，是否啟用規則無法從外部確認
_WAF_CAPABLE = {
    "Cloudflare",
    "Akamai",
    "Imperva",
    "Sucuri",
    "Amazon CloudFront",
    "Azure Front Door",
    "Fastly",
}


def _resolver() -> dns.resolver.Resolver:
    resolver = dns.resolver.Resolver()
    resolver.timeout = _TIMEOUT
    resolver.lifetime = _LIFETIME
    return resolver


def _query(name: str, rdtype: str) -> list[str]:
    try:
        return [r.to_text().rstrip(".") for r in _resolver().resolve(name, rdtype)]
    except Exception:  # noqa: BLE001 - 查不到就留空
        return []


def _reverse(ip: str) -> str:
    try:
        answers = _resolver().resolve(dns.reversename.from_address(ip), "PTR")
        return answers[0].to_text().rstrip(".")
    except Exception:  # noqa: BLE001
        return ""


def _network_owner(ip: str) -> str:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    return "Cloudflare" if any(address in net for net in _CLOUDFLARE_NETWORKS) else ""


def _suffix_owner(hostname: str) -> str:
    hostname = hostname.lower()
    for provider, suffixes in _HOSTNAME_SUFFIXES:
        if any(hostname == s or hostname.endswith("." + s) for s in suffixes):
            return provider
    return ""


def detect_edge(headers: dict, addresses: list[dict], cnames: list[str]) -> dict | None:
    """綜合標頭、IP 網段、CNAME、反解判斷邊緣服務；沒有任何訊號回 None。"""
    lowered = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    evidence: list[str] = []
    provider = ""
    for name, matches in _HEADER_SIGNATURES:
        if matches(lowered):
            provider = provider or name
            marker = "cf-ray" if name == "Cloudflare" and "cf-ray" in lowered else "server"
            evidence.append(
                f"回應標頭：{marker}" + (f": {lowered.get(marker)}" if marker == "server" else "")
            )
            break
    for address in addresses:
        if address.get("network"):
            provider = provider or address["network"]
            evidence.append(f"IP {address['ip']} 屬於 {address['network']} 公告的網段")
        elif _suffix_owner(address.get("rdns", "")):
            provider = provider or _suffix_owner(address["rdns"])
            evidence.append(f"IP {address['ip']} 反解為 {address['rdns']}")
    for cname in cnames:
        if _suffix_owner(cname):
            provider = provider or _suffix_owner(cname)
            evidence.append(f"CNAME 指向 {cname}")
    if not provider:
        return None
    return {
        "provider": provider,
        "waf_capable": provider in _WAF_CAPABLE,
        "evidence": list(dict.fromkeys(evidence))[:6],
    }


def edge_notice(edge: dict | None) -> str:
    if not edge:
        return ""
    return (
        f"目前掃描目標位於 {edge['provider']} Edge，而非直接掃描 Origin Server，"
        "因此部分 Port、服務或主機層級資訊可能受到 CDN／Reverse Proxy 架構影響。"
    )


def analyze_infrastructure(hostname: str, headers: dict | None = None) -> dict:
    """回傳 {hostname, addresses:[{ip, version, rdns, network}], cname, nameservers, edge,
    scan_target, notice}。

    scan_target：edge（掃到的是邊緣節點）／origin（直接連到主機）／unknown。
    """
    hostname = (hostname or "").lower().strip(".")
    profile = {
        "hostname": hostname,
        "addresses": [],
        "cname": [],
        "nameservers": [],
        "edge": None,
        "scan_target": "unknown",
        "notice": "",
    }
    if not hostname:
        return profile
    try:
        cnames = _query(hostname, "CNAME")
        ips = (_query(hostname, "A") + _query(hostname, "AAAA"))[:MAX_ADDRESSES]
        addresses = [
            {
                "ip": ip,
                "version": ipaddress.ip_address(ip).version,
                "rdns": _reverse(ip),
                "network": _network_owner(ip),
            }
            for ip in ips
        ]
        zone = hostname[4:] if hostname.startswith("www.") else hostname
        profile.update(
            addresses=addresses,
            cname=cnames,
            nameservers=sorted(_query(zone, "NS")),
        )
        edge = detect_edge(headers or {}, addresses, cnames)
        profile["edge"] = edge
        profile["notice"] = edge_notice(edge)
        if edge:
            profile["scan_target"] = "edge"
        elif addresses:
            profile["scan_target"] = "origin"
    except Exception:  # noqa: BLE001 - 輔助資訊，失敗不影響掃描
        pass
    return profile
