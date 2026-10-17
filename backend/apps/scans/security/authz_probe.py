"""未授權存取探測（確定性 BOLA／Broken Object Level Authorization 補位）。

把 AI Agent 偶然打到的「API 無需登入就回傳成批個資／帳號」沉澱成每次都跑得到的確定性檢查：
對爬取時發現的同網站 API 端點做**無憑證 GET**，若回 200 且內容是成批帳號／成員記錄就報。

**只在「全站＋主動模式＋網域已驗證」時執行**（與 exposure 檔案探測同閘），送請求但不帶任何
認證（全新 context、無 cookie）。

誤報防線（關鍵）：公開網站回傳 JSON 陣列是常態（商品、文章、公開目錄），不能見到 200 JSON
就報。先要是**成批記錄**（頂層陣列，或 data／result／items… 底下的非空物件陣列），再滿足以下
任一條才算未授權記錄外洩：
1. 記錄同時帶**身分欄位**（姓名／帳號／email／電話／member／user…）**與內部帳號欄位**
   （memberId／roleId／啟用狀態／建立或修改時間…）——後台帳號／成員名單。公開人員目錄
   通常只有姓名職稱、沒有內部 id 與帳號狀態，用「內部欄位」這條把它們排除。
2. 出現**敏感欄位名**（password／token／secret／身分證／idcard／ssn）——絕不可能刻意成批公開。
3. 回應夾帶**強個資**（身分證／信用卡）——同上，不需再要求欄位名。
email／手機屬弱個資（公開聯絡清單也會有），不單獨成立，只在第 1 條成立時把嚴重度升到 high。
"""

from __future__ import annotations

import json
import re

from config.egress import playwright_launch_kwargs
from django.conf import settings

from apps.scans.cancellation import ScanCancelled
from apps.scans.scanners import detect_pii_in_text, make_finding
from apps.scans.security.exposure_scanner import _PacedRequester
from apps.scans.security.redaction import redact_pii_in_text, redact_url_query_values
from apps.scans.security.secret_scanner import redact_secrets_in_text
from apps.scans.services import assert_public_http_url

# 每次掃描最多探測幾個端點（送無憑證請求，受 active RPS 限制，數量要有上限）。
# 預設值；實際以 settings.ARGUS_AUTHZ_PROBE_MAX_ENDPOINTS 為準（ADR-0005 §3 放寬，不限重抓）。
MAX_ENDPOINTS = 60


def _max_endpoints() -> int:
    return max(int(getattr(settings, "ARGUS_AUTHZ_PROBE_MAX_ENDPOINTS", MAX_ENDPOINTS)), 1)

# 成批記錄常見的外層鍵（REST 包一層 {data:[...]}）
_LIST_KEYS = ("data", "result", "results", "items", "list", "rows", "content", "records")

# 身分欄位：記錄是在描述「人／帳號」
_IDENTITY_KEYS = re.compile(
    r"(name|姓名|email|mail|phone|tel|mobile|手機|電話|username|account|帳號"
    r"|member|user|使用者|會員|student|學號|employee)",
    re.I,
)
# 內部帳號欄位：公開目錄通常沒有，用來區隔「刻意公開」與「後台外洩」
_INTERNAL_KEYS = re.compile(
    r"(memberid|member_id|userid|user_id|roleid|role_id|rolename|role"
    r"|isactive|is_active|enabled|啟用|狀態|status|createtime|create_time|建立"
    r"|updatetime|update_time|modifytime|修改|lastlogin|password|passwd|pwd|token|secret)",
    re.I,
)
# 一定敏感的欄位：出現就直接 high
_SENSITIVE_KEYS = re.compile(r"(password|passwd|pwd|token|secret|身分證|idcard|id_card|ssn)", re.I)

_SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _record_objects(parsed: object) -> list[dict]:
    """從解析後的 JSON 取出「成批記錄」（物件陣列）；取不到回 []。"""
    if isinstance(parsed, list):
        objs = [x for x in parsed if isinstance(x, dict)]
        return objs if len(objs) >= 1 and len(parsed) >= 2 else []
    if isinstance(parsed, dict):
        for key in _LIST_KEYS:
            value = parsed.get(key)
            if isinstance(value, list):
                objs = [x for x in value if isinstance(x, dict)]
                if len(objs) >= 2:
                    return objs
    return []


def _collect_keys(objects: list[dict]) -> set[str]:
    keys: set[str] = set()
    for obj in objects[:20]:
        keys.update(str(k) for k in obj.keys())
    return keys


def analyze_unauthorized_results(results: list[dict]) -> list[dict]:
    """把無憑證探測的 raw 結果轉成 Finding（純函式）。保守判定，見模組 docstring 的三條防線。"""
    findings: list[dict] = []
    for r in results or []:
        try:
            status = int(r.get("status") or 0)
        except (TypeError, ValueError):
            continue
        if status != 200:
            continue
        body = r.get("body") or ""
        ctype = str(r.get("content_type") or "").lower()
        if "json" not in ctype and not body.lstrip().startswith(("{", "[")):
            continue
        try:
            parsed = json.loads(body)
        except (ValueError, TypeError):
            continue
        objects = _record_objects(parsed)
        if not objects:
            continue
        keys = _collect_keys(objects)
        keys_blob = " ".join(keys)
        pii = detect_pii_in_text(body)
        pii_total = sum(len(v) for v in pii.values())
        # 身分證／信用卡＝絕不可能刻意公開的強個資；email／手機是公開聯絡清單也會有的弱個資
        strong_pii = bool(pii.get("national_id") or pii.get("credit_card"))
        has_identity = bool(_IDENTITY_KEYS.search(keys_blob))
        has_internal = bool(_INTERNAL_KEYS.search(keys_blob))
        has_sensitive_keys = bool(_SENSITIVE_KEYS.search(keys_blob))
        # 成立條件（任一）：
        #   1. 身分欄位＋內部帳號欄位——後台帳號／成員名單（公開目錄沒有內部欄位，用這條區隔）
        #   2. 敏感欄位名（password／token／身分證…）——這些欄位絕不可能刻意成批公開
        #   3. 強個資（身分證／信用卡）出現在回應——同上，不需再要求欄位名
        # email／手機這類弱個資不單獨成立（公開聯絡清單也有），要配合第 1 條的內部欄位。
        if not ((has_identity and has_internal) or has_sensitive_keys or strong_pii):
            continue

        url = r.get("url") or ""
        safe_url = redact_pii_in_text(redact_url_query_values(str(url)))
        severity = "high" if (pii_total > 0 or has_sensitive_keys or strong_pii) else "medium"

        sample_keys = sorted(keys)[:15]
        excerpt = redact_pii_in_text(redact_secrets_in_text(body)).strip()[:400]
        evidence_parts = [
            f"命中（無登入憑證）：GET {safe_url} → HTTP 200",
            f"回傳成批記錄：約 {len(objects)} 筆，欄位含 {', '.join(sample_keys)}",
        ]
        if pii_total > 0:
            evidence_parts.append(
                "偵測到疑似個資：" + ", ".join(f"{k}×{len(v)}" for k, v in pii.items() if v)
            )
        if excerpt:
            evidence_parts.append("回應片段（個資與秘鑰已遮罩）：\n" + excerpt)

        description = (
            f"API 端點 {safe_url} 無需任何登入憑證即回傳成批記錄"
            f"（約 {len(objects)} 筆，含個資或內部帳號資料）。"
            "這類後台資料應只開放給已驗證的管理員，匿名可讀代表存取控制缺失，"
            "攻擊者可一次撈走整份名單。"
        )
        if pii_total > 0:
            description += f"\n⚠️ 回傳內容含 {pii_total} 筆疑似個資，請依個資法妥善處理本報告。"

        findings.append(make_finding(
            category="security",
            severity=severity,
            rule_id="security-unauth-api-records",
            title="API 無需登入即回傳成批帳號／成員記錄",
            description=description,
            remediation=(
                "在該 API 前加上身份驗證與授權中介層（如 JWT／Session 檢查），確認只有登入且"
                "具權限的使用者才能呼叫；若必須公開，對回傳欄位做最小揭露（移除內部識別碼、"
                "帳號狀態、時間戳與個資）。"
            ),
            evidence="\n\n".join(evidence_parts),
            evidence_source="authz_probe",
            evidence_json={
                "endpoint": _path_of(url),
                "record_count": len(objects),
                "assessment": {
                    "condition": "這個 API 不需登入，就能從網際網路直接取得成批記錄。",
                    "observed": "主動探測以未登入請求取得回應（見檢測依據；個資與秘鑰已遮罩）。",
                    "missing": "未進一步測試能否逐筆越權取得他人資料（IDOR），也未驗證資料敏感度。",
                    "verify": "用未登入的瀏覽器直接開啟該網址；修補後應回 401 或 403。",
                },
            },
            impact_area="broken_access_control",
            confidence=0.9,
            priority_score=70.0 if severity == "high" else 50.0,
        ))
    return findings


def _path_of(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).path.rstrip("/").lower() or "/"


async def probe_unauthorized_endpoints(
    candidate_urls: list[str], scan_job_id: int,
) -> list[dict]:
    """對候選 API 端點做無憑證 GET，回傳 raw 結果。任何例外回已收集結果（不影響主掃描）。"""
    from playwright.async_api import async_playwright  # 延遲匯入

    max_endpoints = _max_endpoints()
    urls: list[str] = []
    seen: set[str] = set()
    for raw in candidate_urls:
        try:
            safe = assert_public_http_url(raw)
        except Exception:
            continue
        if safe not in seen:
            seen.add(safe)
            urls.append(safe)
        if len(urls) >= max_endpoints:
            break

    results: list[dict] = []
    if not urls:
        return results
    rps = max(getattr(settings, "ARGUS_ACTIVE_MAX_RPS", 2), 1)
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, **playwright_launch_kwargs())
            context = await browser.new_context(user_agent=settings.ARGUS_SCANNER_USER_AGENT)
            try:
                requester = _PacedRequester(context, scan_job_id, 1.0 / rps)
                for url in urls:
                    try:
                        resp = await requester.get(url, timeout=12000)
                    except ScanCancelled:
                        raise
                    except Exception:
                        continue
                    body = ""
                    if resp.status == 200:
                        try:
                            body = (await resp.text())[:20000]
                        except Exception:
                            body = ""
                    results.append({
                        "url": url,
                        "status": resp.status,
                        "content_type": (resp.headers or {}).get("content-type", ""),
                        "body": body,
                    })
            finally:
                await context.close()
                await browser.close()
    except ScanCancelled:
        raise
    except Exception:
        return results
    return results
