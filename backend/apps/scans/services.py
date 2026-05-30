from urllib.parse import urlparse

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


def normalize_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if not parsed.scheme:
        parsed = urlparse(f"https://{raw_url.strip()}")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("請輸入有效的 HTTP 或 HTTPS 網址。")
    hostname = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{hostname}{port}{path}{query}"


def get_origin(url: str) -> str:
    parsed = urlparse(url)
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def get_hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def is_obvious_third_party(hostname: str) -> bool:
    if hostname in OBVIOUS_THIRD_PARTY_DOMAINS:
        return True
    if any(hostname.endswith(f".{domain}") for domain in OBVIOUS_THIRD_PARTY_DOMAINS):
        return True
    return any(keyword in hostname for keyword in BANK_KEYWORDS)


def get_client_ip(request) -> str:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")

