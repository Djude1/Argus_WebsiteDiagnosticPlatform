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
from urllib.parse import urlparse, urlunparse

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

# IDOR／BOLA 枚舉：路徑最後一段是純數字 id 的端點（/api/Users/29、/rest/basket/1…），
# 換個 id 看能不能未授權取得別人的物件。鄰近 id 與每次掃描最多探幾個模板。
_ID_SEGMENT = re.compile(r"^\d{1,9}$")
_IDOR_PROBE_IDS = (1, 2, 3)
MAX_IDOR_TEMPLATES = 5


def _id_template(path: str) -> tuple[str, int] | None:
    """路徑最後一段是純數字 id → 回 (模板, id)，否則 None。

    `/api/Users/29` → (`/api/users/#`, 29)。只認純數字結尾（避免把 UUID／slug 當 id 枚舉，
    控制誤報與請求量）。
    """
    parts = [p for p in (path or "").split("/") if p]
    if len(parts) < 2 or not _ID_SEGMENT.match(parts[-1]):
        return None
    template = "/" + "/".join([*parts[:-1], "#"])
    return template.lower(), int(parts[-1])


def _sensitivity(keys_blob: str, pii: dict) -> tuple[bool, bool, bool]:
    """共用判定門檻（成批名單與單筆 IDOR 共用）：回 (是否成立, 有敏感欄位名, 有強個資)。

    成立＝身分欄位＋內部帳號欄位（後台名單）／敏感欄位名／強個資（身分證／信用卡）任一。
    email／手機屬弱個資，不在此單獨成立（由呼叫端另計 pii_total 升嚴重度）。
    """
    strong_pii = bool(pii.get("national_id") or pii.get("credit_card"))
    has_identity = bool(_IDENTITY_KEYS.search(keys_blob))
    has_internal = bool(_INTERNAL_KEYS.search(keys_blob))
    has_sensitive = bool(_SENSITIVE_KEYS.search(keys_blob))
    qualifies = (has_identity and has_internal) or has_sensitive or strong_pii
    return qualifies, has_sensitive, strong_pii


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
        # 成立條件（任一，見 _sensitivity）：身分欄位＋內部帳號欄位／敏感欄位名／強個資。
        # email／手機這類弱個資不單獨成立（公開聯絡清單也有），要配合內部欄位。
        qualifies, has_sensitive_keys, strong_pii = _sensitivity(keys_blob, pii)
        if not qualifies:
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
    return urlparse(url).path.rstrip("/").lower() or "/"


def expand_idor_candidates(urls: list[str]) -> list[str]:
    """對結尾是數字 id 的端點，補上「父集合」與「鄰近 id」當額外探測目標（通用、不寫死路徑）。

    - 父集合（去掉結尾 id）：淺爬只觀察到 `/x/2`，成批外洩其實在父集合 `/x`。
    - 鄰近 id（1／2／3 ＋觀察到的那個）：給 IDOR 枚舉用——同模板不同 id 都能未授權取得就是 BOLA。

    每個模板只展開一次、最多 MAX_IDOR_TEMPLATES 個模板，避免請求量爆開；回傳的額外 URL 由
    呼叫端併進既有候選後統一去重與套用 MAX_ENDPOINTS 上限。
    """
    extra: list[str] = []
    seen_templates: set[str] = set()
    for raw in urls:
        parsed = urlparse(raw)
        info = _id_template(parsed.path)
        if not info:
            continue
        template, observed_id = info
        if template in seen_templates:
            continue
        seen_templates.add(template)
        if len(seen_templates) > MAX_IDOR_TEMPLATES:
            break
        parent_path = template[: -len("/#")]  # 去掉結尾 "/#"
        id_prefix = template[:-1]  # 結尾 "#" 之前（含斜線）
        paths = [parent_path] + [
            f"{id_prefix}{i}" for i in sorted(set(_IDOR_PROBE_IDS) | {observed_id})
        ]
        for path in paths:
            extra.append(urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")))
    return extra


def analyze_idor_results(results: list[dict]) -> list[dict]:
    """單筆物件型 IDOR／BOLA：同一 `/:id` 模板下，未授權換 id 取得不同使用者的物件即報。

    保守判定：同一模板要有 ≥2 個不同 id 都回 200、內容是**不同的**單一物件（排除所有 id 回同一頁
    的 SPA／靜態頁），且物件帶身分／內部／個資欄位（_sensitivity，排除公開的 /產品/:id 目錄）。
    """
    groups: dict[str, dict[int, tuple[dict, str, str]]] = {}
    for r in results or []:
        try:
            status = int(r.get("status") or 0)
        except (TypeError, ValueError):
            continue
        if status != 200:
            continue
        url = r.get("url") or ""
        info = _id_template(urlparse(url).path)
        if not info:
            continue
        template, ident = info
        body = r.get("body") or ""
        ctype = str(r.get("content_type") or "").lower()
        if "json" not in ctype and not body.lstrip().startswith("{"):
            continue
        try:
            parsed = json.loads(body)
        except (ValueError, TypeError):
            continue
        record = _single_record(parsed)
        if record is None:
            continue
        groups.setdefault(template, {}).setdefault(ident, (record, body, url))

    findings: list[dict] = []
    for template, by_id in groups.items():
        # 需要 ≥2 個不同 id、且回應內容互異（全一樣＝靜態頁，不是逐物件資料）
        qualifying: list[tuple[int, dict, str, str]] = []
        seen_bodies: set[str] = set()
        for ident, (record, body, url) in sorted(by_id.items()):
            keys_blob = " ".join(str(k) for k in record.keys())
            pii = detect_pii_in_text(body)
            qualifies, has_sensitive, strong_pii = _sensitivity(keys_blob, pii)
            norm = " ".join(body.split())
            if qualifies and norm not in seen_bodies:
                seen_bodies.add(norm)
                qualifying.append((ident, record, body, url))
        if len(qualifying) < 2:
            continue

        sample = qualifying[0]
        all_pii = detect_pii_in_text("\n".join(q[2] for q in qualifying))
        pii_total = sum(len(v) for v in all_pii.values())
        keys_blob = " ".join(str(k) for q in qualifying for k in q[1].keys())
        _, has_sensitive, strong_pii = _sensitivity(keys_blob, all_pii)
        severity = "high" if (pii_total > 0 or has_sensitive or strong_pii) else "medium"

        ids_hit = [q[0] for q in qualifying]
        template_display = template  # 已含 # 佔位，無查詢字串、無個資
        sample_keys = sorted({str(k) for q in qualifying for k in q[1].keys()})[:15]
        excerpt = redact_pii_in_text(redact_secrets_in_text(sample[2])).strip()[:400]
        evidence_parts = [
            f"命中（無登入憑證）：{template_display} 換 id 皆回 HTTP 200",
            f"至少 {len(ids_hit)} 個不同 id（例：{', '.join(str(i) for i in ids_hit[:5])}）"
            f"回傳內容互異的單筆物件，欄位含 {', '.join(sample_keys)}",
        ]
        if pii_total > 0:
            evidence_parts.append(
                "偵測到疑似個資：" + ", ".join(f"{k}×{len(v)}" for k, v in all_pii.items() if v)
            )
        if excerpt:
            evidence_parts.append("回應片段（個資與秘鑰已遮罩）：\n" + excerpt)

        description = (
            f"物件端點 {template_display} 不需任何登入憑證，只要改網址裡的數字 id 就能取得"
            "不同使用者／物件的完整資料（典型的 IDOR／BOLA 存取控制缺失）。"
            "攻擊者可直接枚舉 id 一筆一筆撈走所有人的資料。"
        )
        if pii_total > 0:
            description += f"\n⚠️ 回傳內容含 {pii_total} 筆疑似個資，請依個資法妥善處理本報告。"

        findings.append(make_finding(
            category="security",
            severity=severity,
            rule_id="security-idor-enumerable-object",
            title="改網址 id 即可取得他人物件（未授權 IDOR）",
            description=description,
            remediation=(
                "在該端點加上物件層級授權檢查：確認目前登入者有權存取這筆 id 的資料"
                "（owner 或具權限角色），否則回 401／403；不要只靠「知道 id」當保護。"
            ),
            evidence="\n\n".join(evidence_parts),
            evidence_source="authz_probe",
            evidence_json={
                "endpoint": template,
                "ids_observed": ids_hit[:10],
                "assessment": {
                    "condition": "這個端點不需登入，改 id 就能取得不同人的物件。",
                    "observed": "主動探測以未登入請求對多個 id 取得內容互異的物件（見檢測依據）。",
                    "missing": "未進一步確認資料敏感度，也未測寫入型越權（改／刪他人物件）。",
                    "verify": "用未登入的瀏覽器開啟兩個不同 id；修補後非本人資料應回 401 或 403。",
                },
            },
            impact_area="broken_access_control",
            confidence=0.9,
            priority_score=70.0 if severity == "high" else 50.0,
        ))
    return findings


def _single_record(parsed: object) -> dict | None:
    """單一物件（IDOR 回傳一筆）：dict 本身，或 {data:{...}}／{result:{...}} 包一層的非空物件。

    頂層是陣列（成批名單）回 None——那是 analyze_unauthorized_results 的範圍，不在這裡重複處理。
    """
    if not isinstance(parsed, dict) or not parsed:
        return None
    for key in _LIST_KEYS:
        inner = parsed.get(key)
        if isinstance(inner, dict) and inner:
            return inner
        if isinstance(inner, list):
            return None  # 包一層的其實是清單，交給成批檢查
    return parsed


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
