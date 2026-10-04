"""網域所有權驗證引擎（主動測試的技術性授權證明）。

主要方法（2026-10-04）：Google Search Console——使用者連接的 Google 帳號在 Search Console
對涵蓋這個網域的資源是「擁有者」（permissionLevel=siteOwner）就通過；只有使用者／受限權限不算。
連接 Search Console 時會自動驗證涵蓋該專案網站的資源（`sync_search_console_ownership`）。

備用的三種方法共用一支 token（`argus-site-verification=<token>`）：
- DNS TXT：`_argus-verification.<domain>` TXT（其次 `<domain>` 本身）
- meta tag：首頁 HTML 前 64KB 需同時出現標籤名與 token
- HTML 檔：`/.well-known/argus-verification.txt` 內容 strip 後等於 token

HTTP 驗證抓取一律先過 `services.assert_public_http_url` 的 SSRF 檢查，
與掃描目標同一套公開位址政策；回應以串流讀取、到上限即停。
"""

import ipaddress
import secrets
from datetime import timedelta
from urllib.parse import urlparse

import dns.resolver
import httpx
from django.utils import timezone

from apps.scans.services import allow_private_targets, assert_public_http_url

# DNS 查詢參數：本機 DNS 已知會間歇失敗，固定重試 3 次、每次 timeout 5 秒
DNS_ATTEMPTS = 3
DNS_TIMEOUT_SECONDS = 5.0

# HTTP 抓取參數
HTTP_TIMEOUT_SECONDS = 15.0
HTTP_MAX_BODY_BYTES = 5 * 1024 * 1024  # 回應大小上限 5MB（串流讀取至上限即停）
META_SCAN_BYTES = 64 * 1024  # meta tag 只檢查 HTML 前 64KB
VERIFICATION_TAG = "argus-site-verification"


class DomainValidationError(ValueError):
    """網域輸入無法正規化成可驗證的公開網域。"""


def generate_token() -> str:
    """產生驗證 token（32 字元 hex）。"""
    return secrets.token_hex(16)


def normalize_domain(raw: str) -> str:
    """把任意輸入正規化成可驗證的網域（小寫 hostname）。

    接受帶 scheme／path 的 URL（抽 hostname）；拒絕 IP、localhost 與
    非 FQDN（無點）輸入——比照 services 公開掃描目標政策的精神，
    驗證目標必須是公開註冊網域。

    ARGUS_ALLOW_PRIVATE_TARGETS（僅限 DEBUG）開啟時，放行 localhost、
    單標籤 hostname 與 IP，供 Docker 網路內的受控測試目標（例如
    juice-shop）完成網域驗證閘門。
    """
    value = (raw or "").strip()
    if not value:
        raise DomainValidationError("請輸入要驗證的網域。")
    if "://" not in value:
        value = f"https://{value}"
    try:
        hostname = (urlparse(value).hostname or "").lower().rstrip(".")
    except ValueError as exc:
        raise DomainValidationError("請輸入有效的網域。") from exc
    if not hostname:
        raise DomainValidationError("請輸入有效的網域。")
    bypass = allow_private_targets()
    if hostname in {"localhost", "ip6-localhost"} and not bypass:
        raise DomainValidationError("不允許驗證 localhost。")
    if not bypass:
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            raise DomainValidationError("請輸入網域，不支援以 IP 位址驗證。")
    if "." not in hostname and ":" not in hostname and not bypass:
        raise DomainValidationError("請輸入完整網域（需包含頂級域，例：example.com）。")
    try:
        hostname.encode("idna")
    except UnicodeError as exc:
        raise DomainValidationError("請輸入有效的網域。") from exc
    return hostname


def _query_txt(name: str) -> list[str]:
    """查單一名稱的 TXT 記錄；任何解析失敗都回空 list（由呼叫端重試）。"""
    resolver = dns.resolver.Resolver()
    resolver.timeout = DNS_TIMEOUT_SECONDS
    resolver.lifetime = DNS_TIMEOUT_SECONDS
    try:
        answer = resolver.resolve(name, "TXT")
    except Exception:  # noqa: BLE001 — DNS 例外類型繁雜，統一視為「這次沒查到」
        return []
    records = []
    for rrset in answer:
        # dnspython 的 TXT 以「分段字串」呈現，需串接
        text = "".join(rrset.strings) if hasattr(rrset, "strings") else str(rrset)
        records.append(text)
    return records


def verify_dns_txt(domain: str, token: str) -> tuple[bool, str]:
    """DNS TXT 驗證：找 `argus-site-verification=<token>`。

    先查 `_argus-verification.<domain>`，再查 `<domain>` 本身；整組查詢
    最多重試 3 次（本機 DNS 已知會間歇失敗）。
    """
    expected = f"{VERIFICATION_TAG}={token}"
    names = [f"_{VERIFICATION_TAG}.{domain}", domain]
    found_any = False
    for _ in range(DNS_ATTEMPTS):
        for name in names:
            records = _query_txt(name)
            if records:
                found_any = True
            for record in records:
                if record.strip().lower() == expected:
                    return True, "DNS TXT 驗證成功。"
    if found_any:
        return False, f"已查到 TXT 記錄，但未包含 {expected}。"
    return False, f"連續 {DNS_ATTEMPTS} 次皆未查到 {names[0]} 或 {domain} 的 TXT 記錄。"


def _fetch_body(url: str, max_bytes: int) -> tuple[int, str]:
    """以 SSRF 安心的 httpx 抓取 URL，串流讀取至 max_bytes 即停。

    回傳 (status_code, body)。任何網路／逾時錯誤統一回 (0, "")，由
    呼叫端把情況寫進驗證結果的 detail。
    """
    try:
        with httpx.Client(
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
            with client.stream("GET", url) as response:
                status_code = response.status_code
                chunks: list[bytes] = []
                received = 0
                for chunk in response.iter_bytes():
                    chunks.append(chunk)
                    received += len(chunk)
                    if received >= max_bytes:
                        break
                return status_code, b"".join(chunks)[:max_bytes].decode(
                    "utf-8", errors="replace"
                )
    except httpx.HTTPError:
        return 0, ""


def verify_meta_tag(domain: str, token: str) -> tuple[bool, str]:
    """meta tag 驗證：首頁 HTML 前 64KB 需同時出現標籤名與 token。

    條件刻意從寬（容忍屬性順序與引號差異）：前 64KB 內「標籤名
    argus-site-verification」與「token」同時出現即算過——門檻在於
    token 是本平台產生的祕密，出現在頁面 HTML 即證明控制權。
    """
    try:
        assert_public_http_url(f"https://{domain}/")
    except ValueError as exc:
        return False, str(exc)

    status_code, body = _fetch_body(f"https://{domain}/", META_SCAN_BYTES)
    if status_code == 0:
        return False, f"無法連上 https://{domain}/（逾時或網路錯誤）。"
    if status_code != 200:
        return False, f"首頁回應非 200（{status_code}），無法驗證 meta 標籤。"
    window = body[:META_SCAN_BYTES]
    if VERIFICATION_TAG in window.lower() and token in window:
        return True, "meta 標籤驗證成功。"
    return False, f"首頁 HTML 前 64KB 未找到含 {VERIFICATION_TAG} 與 token 的 meta 標籤。"


def verify_html_file(domain: str, token: str) -> tuple[bool, str]:
    """HTML 檔驗證：`/.well-known/argus-verification.txt` 內容等於 token。"""
    url = f"https://{domain}/.well-known/argus-verification.txt"
    try:
        assert_public_http_url(url)
    except ValueError as exc:
        return False, str(exc)

    status_code, body = _fetch_body(url, HTTP_MAX_BODY_BYTES)
    if status_code == 0:
        return False, f"無法連上 {url}（逾時或網路錯誤）。"
    if status_code != 200:
        return False, f"驗證檔回應非 200（{status_code}）。"
    if body.strip() == token:
        return True, "驗證檔案驗證成功。"
    return False, f"{url} 的內容與 token 不符。"


def verify_search_console(user, domain: str) -> tuple[bool, str]:
    """以使用者已連接的 Search Console 確認是否為涵蓋此網域之資源的擁有者。"""
    from apps.scans.models import SearchConsoleConnection
    from apps.scans.seo import gsc

    if not gsc.is_enabled():
        return False, "網站尚未設定 Google Search Console 串接，請改用其他驗證方式。"
    connections = list(SearchConsoleConnection.objects.filter(user=user))
    if not connections:
        return False, (
            "尚未連接 Google Search Console：請在網域驗證頁按「連接 Google Search Console」。"
        )
    not_owner, errors = "", ""
    for connection in connections:
        try:
            sites = gsc.list_sites(connection)
        except gsc.GscError as exc:
            errors = str(exc)
            continue
        for site in sites:
            if not gsc.property_covers_domain(site["site_url"], domain):
                continue
            if site["permission"] == "siteOwner":
                return True, f"Search Console 確認你是 {site['site_url']} 的擁有者。"
            not_owner = site["site_url"]
    if not_owner:
        return False, f"你在 Search Console 對 {not_owner} 只有使用者權限，需要是「擁有者」。"
    if errors:
        return False, f"讀取 Search Console 失敗：{errors}"
    return False, (
        "連接的 Google 帳號在 Search Console 沒有涵蓋這個網域的資源；"
        "請先在 Search Console 新增並驗證這個網站（建議用「網域」資源）。"
    )


_VERIFIERS = {
    "dns_txt": verify_dns_txt,
    "meta_tag": verify_meta_tag,
    "html_file": verify_html_file,
}


def run_verification(verified_domain, method: str) -> bool:
    """對 VerifiedDomain 執行指定方法的驗證並更新狀態。回傳是否成功。

    成功 → status=verified、verified_at=now、expires_at=now+TTL、
    last_error 清空、method 記錄實際通過的方法。
    失敗 → status 停在 pending／expired（已過期的續驗）並記錄 last_error；
    rejected（人工否決）不因驗證失敗翻動。
    """
    if method == "search_console":
        def verifier(domain, _token):
            return verify_search_console(verified_domain.user, domain)
    else:
        verifier = _VERIFIERS.get(method)
    if verifier is None:
        raise ValueError(f"不支援的驗證方法：{method}")

    now = timezone.now()
    # 已驗證但過期的續驗：先收斂成 expired，失敗時就停在 expired
    if (
        verified_domain.status == verified_domain.Status.VERIFIED
        and verified_domain.expires_at is not None
        and verified_domain.expires_at <= now
    ):
        verified_domain.status = verified_domain.Status.EXPIRED

    ok, detail = verifier(verified_domain.domain, verified_domain.token)
    _apply_result(verified_domain, method, ok, detail, now)
    return ok


def _apply_result(verified_domain, method: str, ok: bool, detail: str, now) -> None:
    verified_domain.last_checked_at = now
    if ok:
        verified_domain.status = verified_domain.Status.VERIFIED
        verified_domain.method = method
        verified_domain.verified_at = now
        verified_domain.expires_at = now + timedelta(days=verified_domain.ttl_days())
        verified_domain.last_error = ""
    else:
        # 失敗：pending 維持 pending、expired 維持 expired、rejected 維持人工否決
        verified_domain.last_error = detail[:255]
    verified_domain.save()


def sync_search_console_ownership(connection, project) -> list[str]:
    """連接 Search Console 後：涵蓋這個專案網站、且使用者是擁有者的資源，自動完成網域驗證。

    網域資源記錄該網域（涵蓋子網域），網址前置字元資源記錄該主機。管理員否決的網域不動。
    回傳本次驗證通過的網域。呼叫端負責吞例外（失敗不影響連接）。
    """
    from apps.scans.models import VerifiedDomain
    from apps.scans.seo import gsc

    verified: list[str] = []
    for site in gsc.list_sites(connection):
        if site["permission"] != "siteOwner" or not gsc.property_matches(
            site["site_url"], project.origin
        ):
            continue
        try:
            domain = normalize_domain(gsc.property_domain(site["site_url"]))
        except DomainValidationError:
            continue
        record, _ = VerifiedDomain.objects.get_or_create(
            user=connection.user, domain=domain, defaults={"token": generate_token()}
        )
        if record.status == VerifiedDomain.Status.REJECTED:
            continue
        _apply_result(
            record, VerifiedDomain.Method.SEARCH_CONSOLE, True,
            f"Search Console 確認你是 {site['site_url']} 的擁有者。", timezone.now(),
        )
        verified.append(domain)
    return verified


def sync_owned_domains(connection) -> list[str]:
    """帳號層級同步：Search Console 裡使用者是「擁有者」的資源全部匯入為已驗證網域，
    並順便驗證清單中被這些資源涵蓋、尚未生效的網域。管理員否決的網域不動。回傳通過的網域。
    """
    from apps.scans.models import VerifiedDomain
    from apps.scans.seo import gsc

    owned = [s["site_url"] for s in gsc.list_sites(connection) if s["permission"] == "siteOwner"]
    now = timezone.now()
    verified: list[str] = []
    for site_url in owned:
        try:
            domain = normalize_domain(gsc.property_domain(site_url))
        except DomainValidationError:
            continue
        VerifiedDomain.objects.get_or_create(
            user=connection.user, domain=domain, defaults={"token": generate_token()}
        )
    for record in VerifiedDomain.objects.filter(user=connection.user).exclude(
        status=VerifiedDomain.Status.REJECTED
    ):
        covering = next(
            (url for url in owned if gsc.property_covers_domain(url, record.domain)), None
        )
        if covering is None:
            continue
        _apply_result(
            record, VerifiedDomain.Method.SEARCH_CONSOLE, True,
            f"Search Console 確認你是 {covering} 的擁有者。", now,
        )
        verified.append(record.domain)
    return verified
