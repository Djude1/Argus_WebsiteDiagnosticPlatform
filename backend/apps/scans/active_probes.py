"""主動式資安偵測（T14）。

僅在 scan_mode='active' 且使用者額外授權後執行。所有探測：
- 套用 RPS ≤ 2（per-origin），由 RateLimitedClient 強制。
- 一律加上自訂 User-Agent: SiteSense-AI-Scanner/1.0 (authorized-audit)。
- 僅使用無破壞性 payload（' OR '1'='1 觀察 response 差異、HEAD 探測路徑）。
- 結果以 finding dict 回傳（caller 寫入 Finding 表，category=security）。

涵蓋三類：
1. SQLi boolean-based：對 Page.outgoing_links 中含 query string 的 URL，注入單個
   payload 比較 response length / status；明顯落在 union/error class 才回報。
2. Admin path enumeration：對 origin 探測常見後台路徑（≤100 條），HEAD 200/302/
   401/403 視為命中。
3. 開放目錄列表：對 origin 與部分高機率目錄做 GET，前 4KB 若含 "Index of /" 等
   特徵字串就回報。
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests

UA = "SiteSense-AI-Scanner/1.0 (authorized-audit)"
DEFAULT_TIMEOUT = 10
MAX_ADMIN_PATHS_PER_SCAN = 100
MAX_SQLI_URLS_PER_SCAN = 30
OPEN_DIR_SIGNATURES = (
    "<title>Index of /",
    "<h1>Index of /",
    "Directory listing for /",
)

# 常見後台/敏感路徑字典（≤100 條）
ADMIN_PATH_DICTIONARY = (
    "admin/", "administrator/", "adminpanel/", "admin.php", "admin/login.php",
    "wp-admin/", "wp-login.php", "wp-config.php.bak", "wp-config.php~",
    "user/login", "users/sign_in", "login", "login.php", "signin", "sign-in",
    "auth/login", "console", "manage", "manager/", "manager/html",
    "phpmyadmin/", "phpMyAdmin/", "myadmin/", "pma/", "dbadmin/",
    "cpanel/", "webadmin/", "ispmanager/", "plesk-stat/", "panel/",
    "dashboard", "dashboard/", "admin/dashboard", "control", "controlpanel/",
    "backup/", "backups/", "backup.zip", "backup.tar.gz", "site-backup.zip",
    "config/", "config.php", "config.json", "config.yml", "config.yaml",
    "settings.php", "settings.json", ".env.bak", ".env.local", ".env.production",
    ".git/HEAD", ".git/config", ".git/index", ".svn/entries", ".hg/store",
    ".DS_Store", "Thumbs.db", "robots.txt.bak",
    "server-status", "server-info", "status", "metrics",
    "actuator", "actuator/health", "actuator/env", "actuator/heapdump",
    "api/v1/admin", "api/admin", "api/users", "api/internal",
    "debug", "debug.php", "phpinfo.php", "info.php", "test.php",
    "uploads/", "files/", "tmp/", "temp/", "cache/",
    "private/", "internal/", "staff/", "staff-login",
    "swagger-ui", "swagger-ui.html", "swagger/", "openapi.json", "api-docs",
    "graphql", "graphiql", "explorer", "playground",
    "old/", "backup-old/", "archive/", "_archive/", "_backup/",
    "test/", "tests/", "demo/", "dev/", "staging/",
    "console/", "shell/", "exec", "exec.php", "cmd.php",
)
# 確保不超過 100 條（settings.py 已聲明 ≤100）
ADMIN_PATH_DICTIONARY = ADMIN_PATH_DICTIONARY[:MAX_ADMIN_PATHS_PER_SCAN]

SQLI_PAYLOAD = "' OR '1'='1"
SQLI_ERROR_HINTS = (
    "you have an error in your sql syntax",
    "warning: mysql",
    "unclosed quotation mark",
    "sqlstate",
    "psqlexception",
    "odbc_exec",
    "sqlite3.operationalerror",
)
SQLI_LEN_DIFF_RATIO = 0.3  # 長度差異 >30% 視為可疑


class RateLimitedClient:
    """簡單同步 RPS 限速 client。預設 2 RPS（active 上限）。"""

    def __init__(self, max_rps: int = 2):
        if max_rps <= 0:
            raise ValueError("max_rps must be positive")
        self._interval = 1.0 / max_rps
        self._last_call = 0.0
        self._session = requests.Session()
        self._session.headers["User-Agent"] = UA

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)
        self._last_call = time.monotonic()

    def get(self, url: str, **kwargs) -> requests.Response | None:
        self._throttle()
        try:
            return self._session.get(url, timeout=DEFAULT_TIMEOUT, **kwargs)
        except requests.RequestException:
            return None

    def head(self, url: str, **kwargs) -> requests.Response | None:
        self._throttle()
        try:
            return self._session.head(url, timeout=DEFAULT_TIMEOUT, **kwargs)
        except requests.RequestException:
            return None


# ----- finding helpers -----


def _make_finding(
    severity: str,
    title: str,
    description: str,
    remediation: str,
    evidence: str,
    impact_area: str,
    confidence: float = 0.6,
) -> dict:
    handoff = (
        "我網站有以下資安問題，請協助我分析並提供修復方向：\n"
        f"- 問題類型: security\n"
        f"- 嚴重度: {severity}\n"
        f"- 問題描述: {description}\n"
        f"- 觸發證據: {evidence}\n"
        f"- 修補建議方向: {remediation}\n\n"
        "請依此資訊提供具體修改方向、檢查步驟與注意事項；不要輸出完整修復程式碼。"
    )
    return {
        "category": "security",
        "severity": severity,
        "title": title,
        "description": description,
        "remediation": remediation,
        "evidence": evidence,
        "selector": "",
        "bounding_box": None,
        "impact_area": impact_area,
        "confidence": confidence,
        "ai_handoff_prompt": handoff,
        "priority_score": 80.0 if severity in {"critical", "high"} else 60.0,
    }


# ----- admin path enumeration -----

# soft 404 判斷：body 長度差異低於此比例視為相同頁面（SPA catch-all）
_SOFT_404_SIMILARITY_THRESHOLD = 0.10


def _detect_soft_404_body_len(origin: str, client: RateLimitedClient) -> int | None:
    """打一個隨機 canary 路徑確認站台是否為 soft 404（SPA catch-all）。

    若 canary 回傳 HTTP 200，表示站台對所有不存在路徑都回傳相同頁面，
    回傳 canary 回應的 body 長度作為比較基準；否則回傳 None。
    """
    canary = "__argus_canary_probe_7f3a9b2c__"
    url = urljoin(origin.rstrip("/") + "/", canary)
    resp = client.get(url)
    if resp is not None and resp.status_code == 200:
        return len(resp.text or "")
    return None


def probe_admin_paths(origin: str, client: RateLimitedClient) -> list[dict]:
    """對 origin 探測常見後台路徑；命中即建立 finding。

    soft 404 偵測：若站台對任意路徑回傳 200（SPA / catch-all），
    改用 GET 比較 body 長度；與 canary 頁面相近的 200 視為 soft 404，略過。
    401/403 無論如何都視為真實命中（伺服器主動拒絕，代表路徑存在）。
    """
    findings: list[dict] = []
    soft_404_len = _detect_soft_404_body_len(origin, client)

    for path in ADMIN_PATH_DICTIONARY:
        url = urljoin(origin.rstrip("/") + "/", path)

        if soft_404_len is not None:
            # Soft 404 站台：HEAD 只用來快速排除非 2xx/3xx/4xx，200 需 GET 複驗
            head_resp = client.head(url, allow_redirects=False)
            if head_resp is None:
                continue
            status = head_resp.status_code
            if status not in {200, 301, 302, 401, 403}:
                continue
            if status == 200:
                # 做 GET 取得實際 body，與 canary 比較
                get_resp = client.get(url)
                if get_resp is None:
                    continue
                body_len = len(get_resp.text or "")
                # body 長度與 canary 差異 < 10%，視為 soft 404，略過
                diff_ratio = abs(body_len - soft_404_len) / max(soft_404_len, 1)
                if diff_ratio < _SOFT_404_SIMILARITY_THRESHOLD:
                    continue
        else:
            head_resp = client.head(url, allow_redirects=False)
            if head_resp is None:
                continue
            status = head_resp.status_code
            if status not in {200, 301, 302, 401, 403}:
                continue

        findings.append(
            _make_finding(
                severity="medium" if status in {401, 403} else "high",
                title=f"偵測到可能暴露的後台或敏感路徑：/{path}",
                description=(
                    f"路徑 {url} 回傳 HTTP {status}，可能是後台、設定檔備份或內部端點。"
                    "外部使用者若能枚舉到這類路徑，會增加被暴力嘗試或資訊洩漏的風險。"
                ),
                remediation=(
                    "確認此路徑是否真的需對公開網路開放；若否，限制存取（IP 白名單、"
                    "VPN、移除備份檔）。若是必要端點，加強認證與速率限制，並避免可被列舉的命名。"
                ),
                evidence=f"HEAD {url} → HTTP {status}",
                impact_area="path_enumeration",
            )
        )
    return findings


# ----- open directory listing -----


def probe_open_directory(origin: str, client: RateLimitedClient) -> list[dict]:
    """對 origin 與部分高機率目錄做 GET，偵測開放目錄列表。"""
    findings: list[dict] = []
    candidates = ("", "files/", "uploads/", "images/", "static/", "backup/", "tmp/")
    for path in candidates:
        url = urljoin(origin.rstrip("/") + "/", path)
        resp = client.get(url)
        if resp is None or resp.status_code != 200:
            continue
        body_sample = (resp.text or "")[:4000]
        if any(sig.lower() in body_sample.lower() for sig in OPEN_DIR_SIGNATURES):
            findings.append(
                _make_finding(
                    severity="high",
                    title=f"偵測到開放目錄列表：{path or '/'}",
                    description=(
                        f"URL {url} 直接列出目錄內容，可能洩漏檔案結構與內部資源。"
                        "攻擊者可藉此找到備份、設定或內部文件。"
                    ),
                    remediation=(
                        "在 Web Server 關閉自動 directory listing（Apache: Options -Indexes、"
                        "Nginx: autoindex off）；對無 index 檔的目錄改回 404 或 403。"
                    ),
                    evidence=f"GET {url} → 200 含 directory listing 特徵",
                    impact_area="information_disclosure",
                    confidence=0.85,
                )
            )
    return findings


# ----- SQLi boolean-based -----


def probe_sqli_on_urls(urls: Iterable[str], client: RateLimitedClient) -> list[dict]:
    """對含 query string 的 URL 注入單個無破壞 payload，比較差異。

    限制：
    - 同一 origin 最多取 MAX_SQLI_URLS_PER_SCAN 個有 query 的 URL。
    - 對每個 param 只注入一次。
    """
    findings: list[dict] = []
    tested = 0
    seen_sigs: set[str] = set()
    for raw_url in urls:
        if tested >= MAX_SQLI_URLS_PER_SCAN:
            break
        parsed = urlparse(raw_url)
        if not parsed.query:
            continue
        params = parse_qsl(parsed.query, keep_blank_values=True)
        if not params:
            continue

        baseline_resp = client.get(raw_url)
        if baseline_resp is None:
            continue
        baseline_len = len(baseline_resp.text or "")
        baseline_status = baseline_resp.status_code

        for idx, (key, value) in enumerate(params):
            sig = f"{parsed.path}::{key}"
            if sig in seen_sigs:
                continue
            seen_sigs.add(sig)
            payload_params = list(params)
            payload_params[idx] = (key, value + SQLI_PAYLOAD)
            test_url = urlunparse(parsed._replace(query=urlencode(payload_params, doseq=True)))
            test_resp = client.get(test_url)
            tested += 1
            if test_resp is None:
                continue
            test_text = (test_resp.text or "")
            test_lower = test_text.lower()

            error_hit = any(hint in test_lower for hint in SQLI_ERROR_HINTS)
            length_changed = baseline_len > 0 and abs(
                len(test_text) - baseline_len
            ) / baseline_len > SQLI_LEN_DIFF_RATIO
            status_changed = test_resp.status_code != baseline_status

            if error_hit:
                findings.append(
                    _make_finding(
                        severity="critical",
                        title=f"SQL 錯誤訊息洩漏：參數 {key} 於 {parsed.path}",
                        description=(
                            f"對 {test_url} 注入 boolean payload 後，回應中含 SQL 錯誤特徵字串。"
                            "強烈暗示該參數未做 prepared statement 或 escaping，存在 SQL 注入風險。"
                        ),
                        remediation=(
                            "改用 parameterized query / ORM 綁定變數；"
                            "避免把使用者輸入直接拼進 SQL；"
                            "關閉錯誤訊息對外暴露（DEBUG=False）。"
                        ),
                        evidence=f"GET {test_url} → 含 SQL 錯誤特徵字串",
                        impact_area="sql_injection",
                        confidence=0.9,
                    )
                )
            elif length_changed or status_changed:
                findings.append(
                    _make_finding(
                        severity="medium",
                        title=f"SQLi boolean 差異訊號：參數 {key} 於 {parsed.path}",
                        description=(
                            f"對 {test_url} 注入 boolean payload 後，回應長度或狀態碼與原本明顯不同"
                            f"（baseline {baseline_status}/{baseline_len}B → "
                            f"test {test_resp.status_code}/{len(test_text)}B）。"
                            "需人工複驗是否為 SQL 注入。"
                        ),
                        remediation=(
                            "檢視該參數的後端處理是否使用 parameterized query；"
                            "對輸入做型別與長度檢查。"
                        ),
                        evidence=(
                            f"baseline GET {raw_url} → {baseline_status}/{baseline_len}B；"
                            f"test GET {test_url} → {test_resp.status_code}/{len(test_text)}B"
                        ),
                        impact_area="sql_injection",
                        confidence=0.5,
                    )
                )
    return findings


# ----- entry point -----


def collect_query_urls(pages: Iterable) -> list[str]:
    """從 Page queryset 取出含 query string 的 final_url 集合。"""
    seen: set[str] = set()
    out: list[str] = []
    for page in pages:
        url = page.final_url or page.url
        if "?" in url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def run_active_probes(
    origin: str,
    pages: Iterable,
    client: RateLimitedClient | None = None,
) -> list[dict]:
    """執行三項主動式偵測，回傳 finding dict 列表。

    caller 必須先確認 scan_job.scan_mode == 'active' 且
    scan_job.active_testing_authorized=True；本函式不再重複檢查授權。
    """
    client = client or RateLimitedClient(max_rps=2)
    findings: list[dict] = []
    findings.extend(probe_admin_paths(origin, client))
    findings.extend(probe_open_directory(origin, client))
    findings.extend(probe_sqli_on_urls(collect_query_urls(pages), client))
    return findings
