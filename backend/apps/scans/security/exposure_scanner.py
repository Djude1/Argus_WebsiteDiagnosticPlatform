"""敏感檔案 / 路徑外洩偵測（主動內容探測 content discovery）。

補上 Argus 最大缺口：crawler 只做連結跟隨 BFS，掃不到「沒有任何頁面連到」的
隱藏敏感檔（.env / .git / 備份 / 後台 / actuator / debug API …）。本模組：
1. 以 robots.txt Disallow + 內建高訊號字典組出探測清單。
2. 重用 Playwright（繞 CF）逐一 GET，套速率限制 + 取消檢查點（純讀取、不修改目標）。
3. 對命中檔案做檔案型態分類 + 秘鑰偵測 + PII 偵測，產生新手易讀、含實際外洩片段的 Finding。

僅在全網站且 active + authorized 模式由 tasks.py 呼叫。任何例外 silent-fail。
純分析函式（parse/build/analyze）與 IO（probe_paths）分離，方便單元測試。
"""
from __future__ import annotations

import asyncio
import re
import time
import uuid
from urllib.parse import urljoin, urlparse

from asgiref.sync import sync_to_async
from config.egress import playwright_launch_kwargs
from django.conf import settings

from apps.scans.cancellation import ScanCancelled, is_cancelled
from apps.scans.scanners import detect_pii_in_text, make_finding
from apps.scans.security.ip_context import describe_ips, private_ips
from apps.scans.security.redaction import redact_pii_in_text, redact_url_query_values
from apps.scans.security.secret_scanner import (
    detect_secrets_in_text,
    redact_secrets_in_text,
)
from apps.scans.services import assert_public_http_url

# 一次探測的目標上限（避免對目標發出過多請求）
MAX_PROBE_TARGETS = 220

# 內建高訊號敏感路徑字典。取自靶機 CEKB 真實檔案 + 市面常見外洩路徑；
# 含 dotted / 非 dotted / .txt 變體（CF Pages 不送 dotfile，作者常做鏡像）。
BUILTIN_SENSITIVE_PATHS: tuple[str, ...] = (
    # 環境變數 / 秘鑰檔
    ".env", "env", ".env.backup", ".env.production", ".env.local", "assets/.env.backup",
    "aws-credentials.txt", "credentials.json", "secrets.json", "config.json",
    "id_rsa", "id_rsa.txt", "id_rsa.pub.txt", ".npmrc", ".htpasswd",
    # 版本控制外洩
    ".git/config", ".git/HEAD", "git/config", "git/HEAD", ".gitignore",
    ".svn/entries", ".hg/hgrc",
    # 套件 / 部署設定
    "package.json", "package-lock.json", "composer.json", "composer.lock",
    "wrangler.toml", "firebase.json", "web.config", "crossdomain.xml",
    "kubeconfig.yaml", ".dockerenv", "Dockerfile", "docker-compose.yml",
    # 資料庫 / 備份
    "backup.sql", "backup.sql.txt", "dump.sql", "dump.sql.txt", "db.sql",
    "database.sql", "assets/backup.sql.txt", "backup.zip", "site.zip", "www.zip",
    "wp-config.php", "wp-config-old.txt", "wp-config.php.bak",
    # 資訊洩露
    "phpinfo.txt", "phpinfo.php", "info.php", "server-status", "server-info",
    # 檔案傳輸目錄與監控指標：上線殘留的 FTP 目錄（目錄列表）與 Prometheus
    # metrics 外露都是真實網站常見的偵察情報洩漏
    "ftp", "ftp/", "metrics",
    "ftp/coupons_2013.md.bak",
    ".DS_Store", "ds_store.txt", "Thumbs.db", "Thumbs.db.txt",
    # 記錄檔
    "access.log", "error.log", "errors.log", "debug.log", "wp-content/debug.log",
    # Spring Boot Actuator（市面超常見）
    "actuator", "actuator/env", "actuator/env.json", "actuator/health.json",
    "actuator/info.json", "actuator/heapdump", "actuator/mappings",
    # API 文件 / 端點
    "swagger.json", "swagger.yaml", "openapi.json", "api-docs", "v2/api-docs", "v3/api-docs",
    "api/graphql", "graphql",
    "api/debug/users.json", "api/v1/users.json", "api/v1/profile.json",
    "api/internal/config.json", "api/internal/health.json",
    # 資料 / PII dump
    "staff.csv", "assets/staff.csv", "staff-list.txt", "users.csv",
    "assets/transactions.json", "plans.json",
    # 原始碼 map
    "script.js.map", "app.js.map", "main.js.map", "bundle.js.map",
    # 開發備註 / 後台
    "dev-notes.txt", "internal-todo.md", "CHANGELOG.md", "release-notes.txt",
    ".well-known/security.txt", "humans.txt", ".claude/launch.json",
    "admin/", "administrator/", "wp-admin/", "wp-login.php",
)


# API 前綴底下也探測的 API 文件路徑（2026-10-16）。網站常把後端放在反向代理前綴後面
# （實測站台：Next.js 把代理前綴轉到 Spring Boot，規格在代理前綴底下的 v3/api-docs），
# 只探測網站根目錄就找不到；這項外洩原本只有 AI Agent 偶然發現，三次掃描只找到一次。
# 只放回傳 JSON 的規格檔：Swagger UI 是 HTML，會被 soft-404 判斷當成 SPA 預設頁。
API_DOC_SUFFIXES: tuple[str, ...] = (
    "v3/api-docs", "v2/api-docs", "api-docs", "swagger.json", "openapi.json",
)
MAX_API_PREFIXES = 5
# 前端資源目錄，不是 API 前綴
_NON_API_SEGMENTS = {"_next", "static", "assets", "images", "img", "css", "js", "fonts", "media"}
# 單段路徑時，第一段本身就是 API 基底才算前綴（rewrite base 在 JS 裡常是裸字串 `/api_proxy`）
_API_BASE_SEGMENT = re.compile(
    r"^(?:api|api[_-]?proxy|backend|rest|graphql|gateway|rpc|v[0-9]+|api-docs|openapi|swagger)$",
    re.IGNORECASE,
)


def api_prefixes(paths: list[str]) -> list[str]:
    """從觀察到或 JS 抽出的同網站 API 路徑推出前綴（第一段，接版本號時連版本一起），最多 5 個。

    `/api_proxy/news/list` → `/api_proxy/`；`/api/v1/users` → `/api/`、`/api/v1/`。
    只有一段時，只有該段本身就是 API 基底（`/api_proxy`、`/graphql`）才當前綴——
    JS 裡 rewrite base 常寫成裸字串 `/api_proxy`，拼接後的路徑才在別處。
    """
    prefixes: list[str] = []
    for path in paths:
        segments = [seg for seg in (path or "").split("/") if seg]
        if not segments or segments[0].lower() in _NON_API_SEGMENTS:
            continue
        if len(segments) < 2:
            if not _API_BASE_SEGMENT.match(segments[0]):
                continue
        candidates = [f"/{segments[0]}/"]
        if len(segments) > 2 and re.fullmatch(r"v\d+", segments[1], re.I):
            candidates.append(f"/{segments[0]}/{segments[1]}/")
        for prefix in candidates:
            if prefix not in prefixes:
                prefixes.append(prefix)
        if len(prefixes) >= MAX_API_PREFIXES:
            break
    return prefixes[:MAX_API_PREFIXES]


def parse_robots_disallow(robots_text: str) -> list[str]:
    """從 robots.txt 抽出所有 Disallow 路徑（去重保序）。空 / 例外回 []。"""
    paths: list[str] = []
    seen: set[str] = set()
    for line in (robots_text or "").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        if key.strip().lower() != "disallow":
            continue
        value = value.strip()
        if value and value != "/" and value not in seen:
            seen.add(value)
            paths.append(value)
    return paths


def build_probe_targets(
    origin: str,
    *,
    robots_disallow: list[str] | None = None,
    api_path_prefixes: list[str] | None = None,
    extra_paths: list[str] | None = None,
) -> list[str]:
    """合併內建字典、API 前綴底下的 API 文件與 robots Disallow，組出 same-origin 探測 URL。

    去重、上限 MAX_PROBE_TARGETS。`extra_paths`（ADR-0006 第 3 刀）是上一次掃描的敏感檔案外洩
    端點，排在最前面確保不被上限截掉——用來重探「是否已修好／仍可讀」。
    """
    targets: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        if not raw:
            return
        full = urljoin(origin + "/", raw.lstrip("/")) if "://" not in raw else raw
        parsed = urlparse(full)
        target_origin = f"{parsed.scheme}://{parsed.hostname}" + (
            f":{parsed.port}" if parsed.port else ""
        )
        if target_origin != origin:
            return
        if full not in seen:
            seen.add(full)
            targets.append(full)

    for path in extra_paths or []:
        _add(path)
    for path in BUILTIN_SENSITIVE_PATHS:
        _add(path)
    for prefix in (api_path_prefixes or [])[:MAX_API_PREFIXES]:
        for suffix in API_DOC_SUFFIXES:
            _add(prefix.rstrip("/") + "/" + suffix)
    for path in robots_disallow or []:
        _add(path)
    return targets[:MAX_PROBE_TARGETS]


# (子字串/後綴 matcher, file_type, base_severity, rule_id, 標籤, 為何危險, 怎麼修)
# 順序：具體者在前，第一個命中者勝出。
_CLASSIFIERS: tuple[tuple[tuple[str, ...], str, str, str, str, str, str], ...] = (
    ((".env", "/env"), "env", "critical", "exposure-file-env", "環境變數檔",
     "環境變數檔通常存放資料庫密碼、API 金鑰等最高機密，外洩等同把鑰匙交給攻擊者。",
     "立即封鎖此檔對外存取並把檔案移出網站根目錄；所有出現過的秘鑰一律重新產生。"),
    ((".git/", "/git/"), "git", "high", "exposure-file-git", "Git 版本控制檔",
     "外洩 .git 可被工具還原完整原始碼與歷史，常含過去誤 commit 的密碼/金鑰。",
     "封鎖 /.git/ 路徑；確認 deploy 流程不要把 .git 一起上傳。"),
    (("aws-credentials", "id_rsa", "credentials.json", "secrets.json", ".htpasswd", ".npmrc"),
     "credentials", "critical", "exposure-file-credentials", "憑證 / 金鑰檔",
     "此類檔案直接存放登入憑證或私鑰，外洩可被直接拿來登入系統或服務。",
     "立即下架並撤銷/輪替所有相關憑證與金鑰。"),
    (("backup.sql", "dump.sql", "db.sql", "database.sql", ".sql", "backup.zip",
      "site.zip", "www.zip", "wp-config"), "backup", "critical", "exposure-file-backup",
     "資料庫 / 原始碼備份檔",
     "備份檔常含整個資料庫（含使用者帳密、個資）或完整原始碼，是高價值攻擊目標。",
     "下架備份檔、移出 web 可存取範圍；改用無法被 web 直接讀取的備份位置。"),
    (("actuator",), "actuator", "critical", "exposure-file-actuator", "Spring Boot Actuator 端點",
     "Actuator 的 env/heapdump 會洩漏環境變數、記憶體內容（含密碼、token），是常見的高危漏洞。",
     "於正式環境停用或鎖定 Actuator 端點（management.endpoints 只開健康檢查並加認證）。"),
    (("api/debug", "users.json", "profile.json", "staff.csv", "transactions.json",
      "users.csv", "staff-list", "plans.json", "internal/config"),
     "data", "high", "exposure-file-data", "資料 / 個資端點",
     "此端點/檔案直接回傳使用者或內部資料，可能含個資、薪資甚至明文密碼。",
     "加上身分驗證與授權；確認 debug / 內部端點不在正式環境對外開放。"),
    (("phpinfo", "info.php"), "phpinfo", "high", "exposure-file-phpinfo", "phpinfo 資訊頁",
     "phpinfo 會洩漏伺服器路徑、模組、環境變數等資訊，方便攻擊者規劃後續攻擊。",
     "刪除 phpinfo 檔，正式環境不要保留任何 debug / info 頁。"),
    (("server-status", "server-info"), "server_status", "high", "exposure-file-server-status",
     "伺服器狀態頁",
     "server-status 會洩漏所有即時請求、內部 IP 與存取路徑，可被用來偵察。",
     "於伺服器設定限制 server-status 只允許本機或特定 IP 存取。"),
    (("metrics", "prometheus"), "metrics", "medium", "exposure-endpoint-metrics",
     "監控 / 指標端點",
     "公開的 /metrics（Prometheus 等）會洩漏內部路由、版本、資源用量與業務指標，"
     "是攻擊者偵察的高價值情報來源。",
     "將指標端點限制於內部網路或加上認證（如 Prometheus 的 basic_auth / mTLS）。"),
    (("swagger", "openapi", "api-docs", "graphql"), "apidoc", "medium", "exposure-file-apidoc",
     "API 文件 / 端點",
     "公開的 API 文件會揭露所有端點與參數，若 API 缺乏授權，攻擊者可照表操課。",
     "確認 API 文件是否需要公開；所有 API 端點實施認證與授權。"),
    ((".js.map",), "sourcemap", "medium", "exposure-file-sourcemap", "原始碼 Source Map",
     "Source map 可把壓縮後的 JS 還原成可讀原始碼，洩漏內部邏輯與隱藏端點。",
     "正式環境不要部署 .map 檔，或封鎖其對外存取。"),
    ((".ds_store", "ds_store", "thumbs.db"), "metadata", "medium", "exposure-file-metadata",
     "系統中繼資料檔",
     ".DS_Store / Thumbs.db 會洩漏目錄下的檔名清單，可被用來找出其他隱藏檔。",
     "刪除這些檔並在部署流程中忽略它們（.gitignore / 上傳排除）。"),
    ((".log", "/logs"), "log", "medium", "exposure-file-log", "記錄檔",
     "記錄檔常含錯誤堆疊、內部路徑、使用者資料甚至 token，外洩有助攻擊者偵察。",
     "封鎖 log 檔對外存取，改放 web 無法讀取的目錄。"),
    (("package.json", "composer.json", "package-lock", "composer.lock", "wrangler.toml",
      "firebase.json", "web.config", "kubeconfig", "docker-compose", "dockerfile",
      "crossdomain.xml", "config.json"), "config", "medium", "exposure-file-config",
     "設定 / 套件清單檔",
     "設定檔會洩漏使用的技術、版本與內部位址，有時還夾帶 token / 連線字串。",
     "確認檔案不含機密；不需要對外的設定檔請封鎖存取。"),
    ((".well-known/security.txt",), "securitytxt", "info", "exposure-securitytxt",
     "security.txt",
     "security.txt 本身是良好實務，但若內含內部聯絡人、測試帳密或內網位址則屬外洩。",
     "保留標準聯絡資訊即可，移除任何內部帳密 / 內網 IP / 測試備註。"),
    (("admin/", "administrator/", "wp-admin", "wp-login", "login"), "admin", "medium",
     "exposure-admin-panel", "後台 / 登入入口",
     "公開可達的後台入口會成為暴力破解與弱密碼攻擊的目標。",
     "限制後台來源 IP、加上強密碼與多因素驗證，避免在頁面/JS 內嵌帳密。"),
    (("dev-notes", "internal-todo", "changelog", "release-notes", "readme", "humans.txt",
      ".claude/"), "devnote", "low", "exposure-file-devnote", "開發備註檔",
     "開發備註可能洩漏內部流程、待辦中的安全弱點或內部位址。",
     "確認備註不含敏感資訊；內部文件不要放在對外網站。"),
)

_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
_PRIORITY = {"critical": 92.0, "high": 78.0, "medium": 55.0, "low": 30.0, "info": 12.0}


def classify_exposure(url: str) -> dict | None:
    """依路徑判斷敏感檔案型態，回傳分類資訊；非敏感回 None。"""
    path = (urlparse(url).path or "").lower()
    for matchers, file_type, severity, rule_id, label, why, fix in _CLASSIFIERS:
        if any(tok in path for tok in matchers):
            return {
                "file_type": file_type, "severity": severity, "rule_id": rule_id,
                "label": label, "why": why, "fix": fix,
            }
    return None


def _looks_like_directory_listing(body: str) -> bool:
    low = (body or "")[:2000].lower()
    # Apache: <title>Index of /...；Express serve-index: <title>listing directory /...
    return (
        "index of /" in low
        or "<title>index of" in low
        or "<title>listing directory" in low
    )


# 預期回傳 HTML 的檔案型態；其餘型態若回 HTML body，多半是 SPA soft-404 fallback
_HTML_EXPECTED_TYPES = {"phpinfo", "server_status", "admin", "dir_listing"}


def _norm_body(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _starts_html_document(body: str) -> bool:
    """body 去掉前導空白與 HTML 註解後，是不是一份 HTML 文件的開頭。

    SPA 的 index.html 常以授權條款註解開頭（juice-shop：`<!-- Copyright… -->` 之後
    才接 `<!doctype html>`），原本只看最前面是不是 doctype／`<html` 會漏判，讓
    `/actuator/env.json`、`/bundle.js.map` 等回同一份 SPA 首頁的 soft-404 被當成真檔案外洩。
    """
    head = body.lstrip()
    # 去掉開頭連續的 HTML 註解（可能有多段）再判斷
    while head.startswith("<!--"):
        end = head.find("-->")
        if end == -1:
            break
        head = head[end + 3:].lstrip()
    low = head[:200].lower()
    return low.startswith("<!doctype html") or low.startswith("<html")


def _is_soft_404(body: str, baselines: list[str]) -> bool:
    """body 與『保證不存在路徑』的 baseline 回應相符 → 視為 SPA / catch-all soft-404。"""
    n = _norm_body(body)
    if not n:
        return False
    for bl in baselines:
        if not bl:
            continue
        if n == bl:
            return True
        # SPA 樣板前綴相同且長度極接近（真實檔前綴會不同）→ 視為 soft-404
        if n[:100] == bl[:100] and abs(len(n) - len(bl)) <= max(20, int(len(bl) * 0.02)):
            return True
    return False


def analyze_probe_results(results: list[dict]) -> list[dict]:
    """把 raw 探測結果（{url,status,content_type,body}）轉成 Finding list（純函式）。

    只處理 2xx 命中。對每個命中檔案：分類 → 跑秘鑰 + PII 偵測 →
    依偵測結果動態提升嚴重度 → 產出含實際外洩片段、新手易讀的 Finding。
    """
    findings: list[dict] = []
    for r in results or []:
        try:
            status = int(r.get("status") or 0)
        except (TypeError, ValueError):
            continue
        if not 200 <= status < 300:
            continue
        # SPA / catch-all 對任意路徑回 200 + 同一頁；soft-404 不是真命中
        if r.get("soft_404"):
            continue
        url = r.get("url") or ""
        safe_url = redact_pii_in_text(redact_url_query_values(str(url)))
        body = r.get("body") or ""
        info = classify_exposure(url)
        if info is None:
            # 未分類但回 200 且 body 像目錄列表 → 仍回報
            if _looks_like_directory_listing(body):
                info = {
                    "file_type": "dir_listing", "severity": "medium",
                    "rule_id": "exposure-dir-listing", "label": "目錄列表",
                    "why": "開啟目錄列表會讓任何人看到目錄下所有檔案，方便攻擊者找隱藏檔。",
                    "fix": "於伺服器關閉 directory listing（如 Apache Options -Indexes）。",
                }
            else:
                continue

        # 非 HTML 型態卻回 HTML body → 多半是 SPA soft-404 fallback（baseline 沒抓到時的保險）
        if info["file_type"] not in _HTML_EXPECTED_TYPES and _starts_html_document(body):
            continue

        secrets = detect_secrets_in_text(body)
        pii = detect_pii_in_text(body)
        pii_total = sum(len(v) for v in pii.values())

        # 動態提升嚴重度：命中秘鑰或個資時，至少 high
        severity = info["severity"]
        if secrets:
            top = max((s["severity"] for s in secrets), key=lambda x: _SEVERITY_ORDER.get(x, 0))
            if _SEVERITY_ORDER[top] > _SEVERITY_ORDER[severity]:
                severity = top
        # security.txt 的聯絡 email 是這個檔案刻意公開的回報窗口（.well-known/security.txt 的用途
        # 就是放 Contact），不因它升到 high；裡頭若有手機／身分證／卡號等其他個資才升級。
        pii_for_upgrade = pii_total
        if info["file_type"] == "securitytxt":
            pii_for_upgrade -= len(pii.get("email", []))
        if pii_for_upgrade > 0 and _SEVERITY_ORDER[severity] < _SEVERITY_ORDER["high"]:
            severity = "high"
        # 對外回應夾帶私有／內部網段 IP（例：OpenAPI 規格的 servers 寫內網位址）＝內部網路
        # 拓樸外洩，是比「只是文件公開」更實質的風險；至少提升到 high。
        internal_ips = private_ips(body)
        if internal_ips and _SEVERITY_ORDER[severity] < _SEVERITY_ORDER["high"]:
            severity = "high"

        # 證據順序：命中 → 內網位址 → 秘鑰 → 個資 → 內容片段。報告的檢測依據只取前 300 字，
        # 重點摘要放在片段之前，否則會被截掉（2026-10-17 實掃：內網 IP 判讀沒出現在報告）。
        evidence_parts = [f"命中：GET {safe_url} → HTTP {status}"]
        if internal_ips:
            host = urlparse(url).hostname or ""
            ip_set = set(internal_ips)
            ip_lines = [
                line for line in describe_ips(body, host)
                if line.split("：", 1)[0] in ip_set
            ]
            evidence_parts.append(
                "內部網路位址外洩（出現在對外回應中）：\n" + "\n".join(ip_lines)
            )
        if secrets:
            sec_lines = "\n".join(f"• {s['label']}：{s['masked']}" for s in secrets[:15])
            evidence_parts.append(f"偵測到 {len(secrets)} 筆疑似秘鑰：\n{sec_lines}")
        if pii_total > 0:
            pii_bits = [f"{k}×{len(v)}" for k, v in pii.items() if v]
            evidence_parts.append(f"偵測到疑似個資：{', '.join(pii_bits)}")
        # 片段在寫 DB 前同時遮罩秘鑰與 PII，避免證據本身造成二次外洩。
        excerpt = redact_pii_in_text(redact_secrets_in_text(body)).strip().replace(
            "\r",
            "",
        )
        if excerpt:
            evidence_parts.append("檔案內容片段：\n" + excerpt[:400])

        description = (
            f"發現可公開存取的{info['label']}：{safe_url}。{info['why']}"
        )
        if secrets:
            description += f"\n⚠️ 此檔內含 {len(secrets)} 筆疑似秘鑰，風險已提升。"
        if pii_total > 0:
            description += f"\n⚠️ 此檔含 {pii_total} 筆疑似個資，請依個資法妥善處理本報告。"
        if internal_ips:
            description += (
                f"\n⚠️ 回應內容夾帶 {len(internal_ips)} 個私有／內部網段 IP"
                f"（{', '.join(internal_ips[:5])}），等同內部網路拓樸外洩，風險已提升。"
            )

        remediation = info["fix"]
        if info["file_type"] == "apidoc":
            remediation += (
                "正式環境若不需要公開，關閉 API 文件與 Swagger UI（例如 springdoc／springfox 的"
                " api-docs、swagger-ui），或在反向代理擋下這些路徑。"
            )
        if internal_ips:
            remediation += (
                "另外移除回應中的內網位址（Swagger 2.0 的 host、OpenAPI 3 的 servers"
                " 改填對外網址或省略）。"
            )

        findings.append(make_finding(
            category="security",
            severity=severity,
            rule_id=info["rule_id"],
            title=f"敏感檔案外洩：{info['label']}",
            description=description,
            remediation=remediation,
            evidence_json={
                "assessment": _probe_assessment(info, internal_ips),
                # 端點路徑供跨層去重用（與 Agent 的 endpoint_path 正規化一致：小寫、去結尾斜線）
                "endpoint": (urlparse(url).path.rstrip("/").lower() or "/"),
            },
            evidence="\n\n".join(evidence_parts),
            evidence_source="exposure_probe",
            impact_area="information_exposure",
            confidence=0.9,
            priority_score=_PRIORITY.get(severity, 50.0),
        ))
    return findings


def _probe_assessment(info: dict, internal_ips: list[str]) -> dict:
    """報告「判定依據」：主動探測已實際取得檔案，不能套用「範本比對未經重現」的預設說法。"""
    if info["file_type"] == "apidoc":
        missing = "只確認規格文件可公開讀取，未測試文件列出的 API 是否缺乏授權"
        missing += "；內網位址能否從外部連線也未驗證。" if internal_ips else "。"
    else:
        missing = "已實際取得檔案；內容的實際影響（例如金鑰是否仍有效）未進一步驗證。"
    return {
        "condition": "這個檔案不需登入，就能從網際網路直接取得。",
        "observed": "主動探測實際下載到檔案內容（見檢測依據；金鑰與個資已遮罩）。",
        "missing": missing,
        "verify": "用未登入的瀏覽器直接開啟該網址；修補後應回 401、403 或 404。",
    }


def analyze_robots_disclosure(disallow: list[str]) -> list[dict]:
    """robots.txt 透過 Disallow 列出敏感路徑本身就是一種資訊洩露（被動，可在任何模式產出）。"""
    sensitive = [
        p for p in (disallow or [])
        if any(tok in p.lower() for tok in (
            ".env", ".git", "backup", "dump", ".sql", "admin", "debug", "actuator",
            "config", "secret", "credential", "internal", "phpinfo", "server-status",
            "id_rsa", "kubeconfig", "swagger", "openapi", ".log",
        ))
    ]
    if len(sensitive) < 3:
        return []
    safe_sensitive = [
        redact_pii_in_text(redact_url_query_values(path))
        for path in sensitive[:30]
    ]
    return [make_finding(
        category="security",
        severity="low",
        rule_id="exposure-robots-disclosure",
        title="robots.txt 洩露敏感路徑清單",
        description=(
            f"robots.txt 以 Disallow 列出了 {len(sensitive)} 條看似敏感的路徑。"
            "Disallow 只是「請搜尋引擎別索引」，並不會阻擋任何人直接存取——"
            "反而等於把敏感檔案的位置整理成一份地圖公開給攻擊者。"
        ),
        remediation=(
            "不要用 robots.txt 來「隱藏」敏感路徑。正確做法是讓這些檔案根本無法被 web 存取"
            "（移出根目錄或加認證），robots.txt 只列真正想控制索引的公開頁面。"
        ),
        evidence=(
            "robots.txt 中的敏感 Disallow：\n"
            + "\n".join(f"• {path}" for path in safe_sensitive)
        ),
        evidence_source="rule_engine",
        impact_area="information_exposure",
        confidence=0.95,
        priority_score=35.0,
    )]


class _PacedRequester:
    """所有 exposure HTTP 請求共用同一個取消檢查與 RPS 時鐘。"""

    def __init__(self, context, scan_job_id: int, min_interval: float) -> None:
        self._context = context
        self._scan_job_id = scan_job_id
        self._min_interval = min_interval
        self._last_at = 0.0

    async def get(self, raw_url: str, *, timeout: int):
        cancelled = await sync_to_async(
            is_cancelled,
            thread_sensitive=True,
        )(self._scan_job_id)
        if cancelled:
            raise ScanCancelled()
        wait = self._min_interval - (time.perf_counter() - self._last_at)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_at = time.perf_counter()
        # max_redirects=0：不跟隨重定向，避免目標站的 open redirect
        # 把探針導向雲端 metadata / 外站（任何重定向會丟例外 → 跳過該路徑）
        return await self._context.request.get(
            assert_public_http_url(raw_url),
            timeout=timeout,
            max_redirects=0,
        )


async def _fetch_robots_disallow(requester: _PacedRequester, origin: str) -> list[str]:
    """主爬蟲沒提供 robots.txt 時自行抓取；失敗回 []。"""
    try:
        robots_url = assert_public_http_url(f"{origin}/robots.txt")
        resp = await requester.get(robots_url, timeout=10000)
        if resp.ok:
            return parse_robots_disallow(await resp.text())
    except ScanCancelled:
        raise
    except Exception:
        pass
    return []


async def _soft_404_baselines(requester: _PacedRequester, origin: str) -> list[str]:
    """soft-404 基準：SPA / catch-all 會對任意路徑回 200 + 同一頁。

    先抓兩個保證不存在的隨機路徑當基準，後續用來濾掉假命中。
    """
    baselines: list[str] = []
    for _ in range(2):
        rnd = f"{origin}/zz-nonexist-{uuid.uuid4().hex}"
        try:
            bresp = await requester.get(rnd, timeout=12000)
            if 200 <= bresp.status < 300:
                baselines.append(_norm_body((await bresp.text())[:20000]))
        except ScanCancelled:
            raise
        except Exception:
            pass
    return baselines


async def _probe_one(requester: _PacedRequester, url: str, baselines: list[str]) -> dict | None:
    """探測單一路徑；連線失敗或被重定向回 None（跳過該路徑）。"""
    try:
        resp = await requester.get(url, timeout=12000)
        status = resp.status
        ctype = (resp.headers or {}).get("content-type", "")
        body = ""
        if 200 <= status < 300:
            try:
                body = (await resp.text())[:20000]
            except Exception:
                body = ""
        return {
            "url": url, "status": status, "content_type": ctype, "body": body,
            "soft_404": (
                _is_soft_404(body, baselines) if 200 <= status < 300 else False
            ),
        }
    except ScanCancelled:
        raise
    except Exception:
        return None


async def probe_paths(
    normalized_url: str,
    origin: str,
    scan_job_id: int,
    *,
    robots_disallow: list[str] | None = None,
    api_path_prefixes: list[str] | None = None,
    extra_paths: list[str] | None = None,
) -> list[dict]:
    """重用 Playwright（繞 CF）探測敏感路徑，回傳 raw 結果。任何例外回 []（不影響主掃描）。

    優先重用主爬蟲取得的 robots.txt Disallow；沒有傳入時才自行抓取。
    套用 active 模式速率限制與取消檢查點。流程：robots → soft-404 基準 → 逐路徑探測，
    三段共用 _PacedRequester 的速率時鐘。
    """
    from playwright.async_api import async_playwright  # 延遲匯入，避免無 worker 環境 import 失敗

    results: list[dict] = []
    rps = max(getattr(settings, "ARGUS_ACTIVE_MAX_RPS", 2), 1)

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                **playwright_launch_kwargs(),
            )
            context = await browser.new_context(
                user_agent=settings.ARGUS_SCANNER_USER_AGENT,
            )
            try:
                requester = _PacedRequester(context, scan_job_id, 1.0 / rps)
                effective_robots_disallow = robots_disallow
                if effective_robots_disallow is None:
                    effective_robots_disallow = await _fetch_robots_disallow(requester, origin)
                targets = build_probe_targets(
                    origin,
                    robots_disallow=effective_robots_disallow,
                    api_path_prefixes=api_path_prefixes,
                    extra_paths=extra_paths,
                )
                baselines = await _soft_404_baselines(requester, origin)
                for url in targets:
                    result = await _probe_one(requester, url, baselines)
                    if result is not None:
                        results.append(result)
            finally:
                await context.close()
                await browser.close()
    except ScanCancelled:
        raise
    except Exception:
        return results
    return results
    return results
