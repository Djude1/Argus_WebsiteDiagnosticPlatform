"""OWASP ZAP 被動分析（roadmap §7、P1/P2 第一步）：只分析爬蟲已經取得的流量，對目標零新增請求。

流程：
1. 爬蟲（`crawl_site(har_dir=...)`）以 Playwright 把同網站的請求與回應錄成
   HAR。
2. `build_har` 整理成一份：只留同 origin、拿掉請求的 Cookie／Authorization、遮蔽 Set-Cookie 的值、
   只保留文字類回應內容並截斷，筆數有上限。
3. 透過 ZAP API 上傳（`core/other/fileUpload`，ZAP 要開 `api.filexfer`）→ `exim/action/importHar` →
   等被動規則佇列清空 → 讀這個 origin 的告警 →
   **清掉告警、網站節點，並把上傳的檔案覆寫成 `{}`**。
4. `alerts_to_findings`：與 Argus 既有檢查重複的規則不另外產生問題（只記「印證」筆數）；
   雜訊類規則略過；
   其餘依 ZAP 風險與信心換成 Argus 嚴重度（信心低降一級、最高到高風險），每條規則合併成一筆。

ZAP 是另外部署的服務（docker compose profile `zap`／k8s optional manifest），
這裡只透過 HTTP API 操作。
ZAP 不會因為匯入 HAR 而對目標發請求；Spider／Active Scan 不在這個模組的範圍。
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from django.core.cache import cache

from apps.scans.scanners import make_finding

# 與 Argus 既有檢查相同的 ZAP 規則：不另外產生問題，避免同一件事報兩次
OVERLAP_RULES = {
    "10010": "Cookie HttpOnly（cookie_scanner）",
    "10011": "Cookie Secure（cookie_scanner）",
    "10020": "X-Frame-Options／frame-ancestors（安全標頭）",
    "10021": "X-Content-Type-Options（安全標頭）",
    "10035": "HSTS（安全標頭）",
    "10038": "CSP（安全標頭）",
    "10055": "CSP 內容（header-csp-unsafe）",
    "10036": "Server 版本（service-version-exposed）",
    "10037": "X-Powered-By（header-x-powered-by）",
    "10202": "表單 CSRF token",
    "10098": "CORS（header-cors-*）",
    "10003": "已知漏洞的 JS 函式庫（js-lib-known-vuln）",
    "90003": "SRI（sri-missing-integrity）",
    "10062": "個資外洩（PII 檢查）",
}
# 只是描述網站性質或幾乎都會出現的資訊類規則，對網站主沒有可行動的意義
IGNORED_RULES = {
    "10109",  # Modern Web Application
    "10049",  # Storable and Cacheable Content
    "10015",  # Re-examine Cache-control Directives
    "10096",  # Timestamp Disclosure
    "10094",  # Base64 Disclosure
    "10050",  # Retrieved from Cache
    "10111",  # Authentication Request Identified
    "10112",  # Session Management Response Identified
    "10113",  # Verification Request Identified
    "10116",  # ZAP is Out of Date
    "90004",  # Insufficient Site Isolation Against Spectre Vulnerability
}
# 常見規則的中文標題與修法；其餘沿用 ZAP 的英文名稱與建議
_ZH = {
    "10017": (
        "引用其他網域的 JavaScript",
        "只引用可信任來源的腳本，並加上 Subresource Integrity（integrity 屬性）。",
    ),
    "10040": (
        "HTTPS 頁面載入 HTTP 資源（混合內容）",
        "把頁面上的資源網址全部改成 https://，或改用相對路徑。",
    ),
    "10027": (
        "原始碼註解含可疑字詞",
        "上線前移除 HTML／JavaScript 註解中的開發備註（TODO、帳號、內部路徑等）。",
    ),
    "10023": (
        "回應含除錯錯誤訊息",
        "關閉正式環境的除錯模式，錯誤頁只顯示一般訊息。",
    ),
    "90022": (
        "回應洩漏應用程式錯誤",
        "攔截例外並回傳一般錯誤頁，詳細錯誤只寫入伺服器記錄。",
    ),
    "10024": (
        "網址含敏感資訊",
        "不要把密碼、token、Email 等放在網址參數，改用 POST 內容或標頭傳遞。",
    ),
    "10063": (
        "缺少 Permissions-Policy 標頭",
        "加上 Permissions-Policy，關閉網站用不到的瀏覽器功能（相機、麥克風、定位等）。",
    ),
    "10054": (
        "Cookie 未設定 SameSite",
        "為 Cookie 加上 SameSite=Lax（或 Strict），跨站情境需要時才用 None 並搭配 Secure。",
    ),
    "2": (
        "回應洩漏內部 IP 位址",
        "移除回應內容或標頭中的內部 IP（10.x、192.168.x 等）。",
    ),
    "3": (
        "Session ID 出現在網址中",
        "Session ID 只放在 Cookie，不要放在網址。",
    ),
    "10044": (
        "轉址回應含大量內容",
        "轉址回應不應附帶頁面內容，避免在未授權的情況下洩漏資料。",
    ),
    "10061": (
        "X-AspNet-Version 標頭洩漏版本",
        "在 web.config 關閉 X-AspNet-Version 標頭。",
    ),
    "10039": (
        "X-Backend-Server 標頭洩漏後端主機",
        "在反向代理移除 X-Backend-Server 標頭。",
    ),
    "10056": (
        "X-Debug-Token 標頭外洩",
        "關閉正式環境的除錯工具列（Symfony Profiler 等）。",
    ),
    "10105": (
        "使用較弱的驗證方式",
        "不要以 HTTP Basic／Digest 在未加密連線上傳送帳密，改用 HTTPS 與表單登入。",
    ),
    "10097": (
        "回應含雜湊值",
        "確認回應中的雜湊值不是密碼或敏感資料的雜湊。",
    ),
    "10041": (
        "HTTPS 頁面的表單送到 HTTP",
        "表單的 action 改成 https://。",
    ),
    "10042": (
        "HTTP 頁面的表單送到 HTTPS",
        "整個網站一律使用 HTTPS，表單頁面也要走 HTTPS。",
    ),
    "10099": (
        "回應洩漏原始碼",
        "確認伺服器沒有把程式原始碼當成文字回傳。",
    ),
}
# ZAP 告警的 risk 是文字（alert/view/alerts 不回傳數字代碼）
_RISK = {"high": "high", "medium": "medium", "low": "low", "informational": "info"}
_DOWNGRADE = {"high": "medium", "medium": "low", "low": "info", "info": "info"}
_TEXT_MIME = re.compile(r"^(text/|application/(json|javascript|xml|xhtml|ld\+json))|\+xml|\+json")
_STRIP_REQUEST_HEADERS = {"cookie", "authorization", "proxy-authorization"}
MAX_LOCATIONS = 10


class ZapError(Exception):
    """ZAP 無法完成被動分析；訊息可寫進 log（不含金鑰與流量內容）。"""


class ZapBusy(ZapError):
    """同一個網站的另一次掃描正在用 ZAP。"""


def enabled() -> bool:
    return bool(
        settings.ARGUS_ZAP_ENABLED and settings.ARGUS_ZAP_API_URL and settings.ARGUS_ZAP_API_KEY
    )


def _same_origin(url: str, origin: str) -> bool:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower() == origin.lower()


def _redact_set_cookie(value: str) -> str:
    """保留 Cookie 名稱與屬性（Secure、HttpOnly…，ZAP 規則要看），值換成固定字串。"""
    name, sep, rest = value.partition("=")
    if not sep:
        return value
    _cookie_value, semi, attributes = rest.partition(";")
    return f"{name}=argus-redacted{semi}{attributes}"


def _clean_entry(entry: dict, max_body_chars: int) -> dict:
    request = dict(entry.get("request") or {})
    request["headers"] = [
        h for h in request.get("headers") or []
        if str(h.get("name", "")).lower() not in _STRIP_REQUEST_HEADERS
    ]
    request["cookies"] = []
    response = dict(entry.get("response") or {})
    response["headers"] = [
        {**h, "value": _redact_set_cookie(str(h.get("value", "")))}
        if str(h.get("name", "")).lower() == "set-cookie" else h
        for h in response.get("headers") or []
    ]
    response["cookies"] = []
    content = dict(response.get("content") or {})
    mime = str(content.get("mimeType", "")).lower()
    if not _TEXT_MIME.search(mime) or content.get("encoding") == "base64":
        content.pop("text", None)
        content.pop("encoding", None)
    elif isinstance(content.get("text"), str):
        content["text"] = content["text"][:max_body_chars]
    response["content"] = content
    return {**entry, "request": request, "response": response}


def build_har(har_paths: list[Path], origin: str) -> tuple[str, int]:
    """合併爬蟲錄下的 HAR，只留同 origin 並去除機密；回傳 (JSON 字串, 筆數)。"""
    entries: list[dict] = []
    for path in har_paths:
        if len(entries) >= settings.ARGUS_ZAP_MAX_ENTRIES:
            break
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for entry in (data.get("log") or {}).get("entries") or []:
            url = str((entry.get("request") or {}).get("url", ""))
            if not _same_origin(url, origin):
                continue
            entries.append(_clean_entry(entry, settings.ARGUS_ZAP_MAX_BODY_CHARS))
            if len(entries) >= settings.ARGUS_ZAP_MAX_ENTRIES:
                break
    har = {"log": {"version": "1.2", "creator": {"name": "Argus", "version": "1"},
                   "entries": entries}}
    return json.dumps(har, ensure_ascii=False), len(entries)


class ZapClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        self.base = base_url.rstrip("/")
        # trust_env=False：ZAP 在叢集內部，不走對外代理
        self.http = httpx.Client(
            timeout=timeout, trust_env=False, headers={"X-ZAP-API-Key": api_key}
        )

    def _call(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = self.http.request(method, f"{self.base}/{path}", **kwargs)
        except httpx.TimeoutException as exc:
            raise ZapError("ZAP 逾時") from exc
        except httpx.HTTPError as exc:
            raise ZapError(f"無法連線到 ZAP（{exc.__class__.__name__}）") from exc
        if response.status_code >= 400:
            code = ""
            try:
                code = response.json().get("code", "")
            except ValueError:
                pass
            raise ZapError(f"ZAP API {path.split('/')[1]}/{path.split('/')[3]} 回應 "
                           f"HTTP {response.status_code}{'（' + code + '）' if code else ''}")
        try:
            return response.json()
        except ValueError as exc:
            raise ZapError("ZAP 回應格式錯誤") from exc

    def view(self, component: str, name: str, **params) -> dict:
        return self._call("GET", f"JSON/{component}/view/{name}/", params=params)

    def action(self, component: str, name: str, **params) -> dict:
        return self._call("GET", f"JSON/{component}/action/{name}/", params=params)

    def version(self) -> str:
        return str(self.view("core", "version").get("version", ""))

    def upload(self, file_name: str, contents: str) -> str:
        data = self._call(
            "POST", "OTHER/core/other/fileUpload/",
            data={"fileName": file_name, "fileContents": contents},
        )
        path = data.get("Uploaded")
        if not path:
            raise ZapError("ZAP 沒有回傳上傳位置（確認已啟用 api.filexfer）")
        return path

    def pending_records(self) -> int:
        return int(self.view("pscan", "recordsToScan").get("recordsToScan", 0))

    def alerts(self, origin: str) -> list[dict]:
        out: list[dict] = []
        while True:
            page = self.view("alert", "alerts", baseurl=origin, start=len(out), count=500)
            batch = page.get("alerts") or []
            out.extend(batch)
            if len(batch) < 500:
                return out

    def clear_origin(self, origin: str) -> None:
        """刪掉這個 origin 的告警與網站節點（錯誤吞掉：清理不能讓掃描失敗）。"""
        try:
            for alert in self.alerts(origin):
                self.action("alert", "deleteAlert", id=alert["id"])
            self.action("core", "deleteSiteNode", url=origin)
        except ZapError:
            pass


@dataclass
class ZapResult:
    version: str = ""
    entries: int = 0
    alerts: list[dict] = field(default_factory=list)
    queue_drained: bool = True


def run_passive(
    har_paths: list[Path], origin: str, scan_id: int,
    *, cancel_check: Callable[[], None] = lambda: None, client: ZapClient | None = None,
) -> ZapResult:
    """把爬到的流量交給 ZAP 被動分析並取回告警；結束後一律清掉 ZAP 上這個網站的資料。"""
    payload, count = build_har(har_paths, origin)
    if not count:
        return ZapResult()
    lock_key = f"argus-zap:{origin.lower()}"
    lock_ttl = int(settings.ARGUS_ZAP_TIMEOUT_SECONDS) + 120
    if not cache.add(lock_key, scan_id, timeout=lock_ttl):
        raise ZapBusy("同一個網站的另一次掃描正在使用 ZAP")
    client = client or ZapClient(settings.ARGUS_ZAP_API_URL, settings.ARGUS_ZAP_API_KEY)
    file_name = f"argus-scan-{scan_id}.har"
    uploaded = False
    try:
        result = ZapResult(version=client.version(), entries=count)
        client.clear_origin(origin)
        path = client.upload(file_name, payload)
        uploaded = True
        client.action("exim", "importHar", filePath=path)
        deadline = time.monotonic() + settings.ARGUS_ZAP_TIMEOUT_SECONDS
        while client.pending_records() > 0:
            cancel_check()
            if time.monotonic() > deadline:
                result.queue_drained = False
                break
            time.sleep(1)
        cancel_check()
        result.alerts = client.alerts(origin)
        return result
    finally:
        client.clear_origin(origin)
        if uploaded:
            try:
                client.upload(file_name, "{}")  # 流量內容不留在 ZAP 主機上
            except ZapError:
                pass
        cache.delete(lock_key)


def _severity(alert: dict) -> str:
    severity = _RISK.get(str(alert.get("risk", "")).lower(), "info")
    if str(alert.get("confidence", "")).lower() == "low":
        severity = _DOWNGRADE[severity]
    return severity


def alerts_to_findings(alerts: list[dict], version: str) -> tuple[list[dict], dict[str, int]]:
    """ZAP 告警 → Argus finding（每條規則一筆）；回傳 (findings, 與既有檢查重複的規則與筆數)。"""
    grouped: dict[str, list[dict]] = {}
    overlap: dict[str, int] = {}
    for alert in alerts:
        plugin = str(alert.get("pluginId", ""))
        if str(alert.get("confidence", "")).lower() == "false positive":
            continue
        if plugin in IGNORED_RULES:
            continue
        if plugin in OVERLAP_RULES:
            overlap[OVERLAP_RULES[plugin]] = overlap.get(OVERLAP_RULES[plugin], 0) + 1
            continue
        grouped.setdefault(plugin, []).append(alert)
    findings = []
    for plugin, items in grouped.items():
        first = items[0]
        severity = max((_severity(a) for a in items), key=["info", "low", "medium", "high"].index)
        title, remediation = _ZH.get(
            plugin, (f"ZAP：{first.get('alert', plugin)}", str(first.get("solution", "")).strip())
        )
        urls = list(dict.fromkeys(a.get("url", "") for a in items))
        locations = [
            {"url": a.get("url", ""), "param": a.get("param", ""),
             "evidence": str(a.get("evidence", ""))[:200]}
            for a in items[:MAX_LOCATIONS]
        ]
        finding = make_finding(
            category="security",
            severity=severity,
            title=title,
            description=(
                f"OWASP ZAP 被動分析在 {len(urls)} 個網址發現「{first.get('alert', '')}」。"
                + str(first.get("description", "")).strip()[:600]
            ),
            remediation=remediation or "依 ZAP 說明確認並修正。",
            evidence="\n".join(
                f"{loc['url']}" + (f"｜{loc['evidence']}" if loc["evidence"] else "")
                for loc in locations
            ),
            rule_id=f"zap-{plugin}",
            evidence_type="zap_alert",
            evidence_source=f"OWASP ZAP {version}（被動分析）".replace("  ", " "),
            evidence_json={
                "source": "zap_passive",
                "plugin_id": plugin,
                "zap_alert": first.get("alert", ""),
                "zap_risk": first.get("risk", ""),
                "zap_confidence": first.get("confidence", ""),
                "count": len(items),
                "locations": locations,
                "reference": str(first.get("reference", "")).split("\n")[0][:300],
            },
        )
        cwe = str(first.get("cweid", ""))
        if cwe.isdigit() and int(cwe) > 0:
            finding["cwe_id"] = f"CWE-{cwe}"
        findings.append(finding)
    return findings, overlap
