"""Katana 補充型爬蟲整合。

透過本機 katana binary 執行，提供：
- JS 端點挖掘（-jc）：從 JS 原始碼解析出隱藏 API 路由
- JS 秘鑰解析（-jsl）：jsluice 深度分析 JS 檔案中的秘鑰與端點
- 技術棧識別（-td）：識別框架/版本，存入 warning_summary.tech_stack

設計原則：
- katana binary 不存在或失敗時靜默回傳空結果，不影響主掃描流程。
- Tech stack 以獨立列表回傳，由 tasks.py 存入 warning_summary。
- 所有 security finding 的 page=None（Finding FK 已是 nullable）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# Vite dev server 路徑特徵：這些路徑若回傳 200 代表原始碼暴露
_VITE_DEV_SIGNATURES = (
    "/@vite/",
    "/@react-refresh",
    "/node_modules/.vite/",
    "/node_modules/vite/",
    "/@fs/",
)

# 原始碼路徑特徵：.jsx/.tsx/.vue 暴露代表 dev server 在 production
_SOURCE_EXT_SIGNATURES = (".jsx", ".tsx", ".vue", ".svelte")

# 秘鑰類型嚴重度映射
_SECRET_SEVERITY: dict[str, str] = {
    "aws": "critical",
    "google": "critical",
    "gcp": "critical",
    "github": "critical",
    "gitlab": "critical",
    "stripe": "critical",
    "twilio": "critical",
    "sendgrid": "critical",
    "openai": "critical",
    "anthropic": "critical",
    "jwt": "high",
    "private key": "critical",
    "rsa": "critical",
    "password": "high",
    "secret": "high",
    "token": "high",
    "api_key": "high",
    "apikey": "high",
}


def _evidence_metadata(rule_id: str, evidence: str, source: str) -> dict:
    return {
        "rule_id": rule_id,
        "evidence_type": "katana_jsonl",
        "evidence_json": {
            "type": "katana_jsonl",
            "source": source,
            "excerpt": evidence[:1000],
        },
        "evidence_source": source,
        "ai_explanation": "",
        "ai_remediation": "",
        "llm_model": "",
        "llm_generated_at": None,
    }


def _rule_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10].upper()
    return f"{prefix}_{digest}"


def run_katana(
    url: str,
    max_depth: int = 3,
    max_pages: int = 50,
) -> tuple[list[dict], list[str]]:
    """以本機 katana binary 執行並回傳 (findings, tech_stack)。

    max_pages 保留於簽名供未來加入爬行頁數上限使用，目前由 katana 自行決定。
    任何錯誤（binary 不存在、timeout、parse 失敗）皆靜默回傳 ([], [])。
    """
    if not shutil.which("katana"):
        logger.warning("katana_scanner: katana binary 不存在，略過")
        return [], []

    timeout = getattr(settings, "KATANA_TIMEOUT", 90)

    cmd = [
        "katana",
        "-u", url,
        "-d", str(max_depth),
        "-jc",
        "-jsl",
        "-td",
        "-j",
        "-silent",
        "-timeout", "10",
        "-rl", "10",
        "-c", "5",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning("katana_scanner: Katana 超時（%ds），略過", timeout)
        return [], []
    except Exception as exc:  # noqa: BLE001
        logger.warning("katana_scanner: 執行失敗 %s，略過", exc.__class__.__name__)
        return [], []

    if result.returncode != 0 and not result.stdout.strip():
        logger.warning(
            "katana_scanner: exit=%d stderr=%s",
            result.returncode,
            result.stderr[:200],
        )
        return [], []

    return _parse_jsonl_lines(result.stdout.splitlines())


def _parse_jsonl_lines(lines: list[str]) -> tuple[list[dict], list[str]]:
    """解析 Katana JSONL 輸出，回傳 (findings, tech_stack)。"""
    findings: list[dict] = []
    tech_set: set[str] = set()
    vite_dev_reported = False  # 同一次掃描只回報一次 Vite dev server 警告

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        # 技術棧識別
        for tech in _extract_technologies(record):
            tech_set.add(tech)

        # jsluice 秘鑰 findings
        findings.extend(_extract_jsluice_findings(record))

        # Vite dev server 暴露偵測
        if not vite_dev_reported:
            vite_finding = _detect_vite_dev_exposure(record)
            if vite_finding:
                findings.append(vite_finding)
                vite_dev_reported = True

        # 隱藏 API 端點偵測
        endpoint_finding = _extract_endpoint_finding(record)
        if endpoint_finding:
            findings.append(endpoint_finding)

    return findings, sorted(tech_set)


def _extract_technologies(record: dict[str, Any]) -> list[str]:
    """從 JSONL 記錄提取技術棧清單（response.technologies 為字串列表）。"""
    response = record.get("response") or {}
    raw = response.get("technologies") or []
    if isinstance(raw, list):
        return [item.strip() for item in raw if isinstance(item, str) and item.strip()]
    return []


def _extract_jsluice_findings(record: dict[str, Any]) -> list[dict]:
    """從 jsluice 欄位提取秘鑰 finding。

    Katana -jsl 輸出的秘鑰資訊可能在：
    - record["jsluice"]
    - record["jsluice"]["secrets"]
    """
    findings: list[dict] = []
    endpoint = (record.get("request") or {}).get("endpoint", "")

    jsluice = record.get("jsluice")
    if not jsluice:
        return findings

    # jsluice 可能是列表或 dict
    candidates: list[Any] = []
    if isinstance(jsluice, list):
        candidates = jsluice
    elif isinstance(jsluice, dict):
        s = jsluice.get("secrets") or []
        if isinstance(s, list):
            candidates = s

    for secret in candidates:
        if not isinstance(secret, dict):
            continue
        finding = _build_secret_finding(secret, endpoint)
        if finding:
            findings.append(finding)

    return findings


def _build_secret_finding(secret: dict[str, Any], endpoint: str) -> dict | None:
    """將單筆 secret 記錄轉為 Argus finding dict。"""
    secret_type = str(
        secret.get("type") or secret.get("name") or secret.get("kind") or "secret"
    ).strip()
    match_val = str(
        secret.get("match") or secret.get("value") or secret.get("secret") or ""
    ).strip()
    line_no = secret.get("line") or secret.get("line_number") or ""

    if not secret_type and not match_val:
        return None

    # 依類型決定嚴重度
    severity = "high"
    for keyword, sev in _SECRET_SEVERITY.items():
        if keyword in secret_type.lower() or keyword in match_val.lower():
            severity = sev
            break

    # 遮罩敏感值（只保留前 6 字元）
    masked = (match_val[:6] + "…") if len(match_val) > 6 else match_val

    evidence_parts = [f"來源：{endpoint}"]
    if line_no:
        evidence_parts.append(f"行號：{line_no}")
    evidence_parts.append(f"比對值（遮罩）：{masked}")

    evidence = "；".join(evidence_parts)
    return {
        "category": "security",
        "severity": severity,
        **_evidence_metadata(
            _rule_id("KATANA_JS_SECRET", f"{endpoint}:{secret_type}:{line_no}"),
            evidence,
            "katana_jsluice",
        ),
        "title": f"JS 檔案含硬編碼秘鑰：{secret_type}",
        "description": (
            f"在 {endpoint} 偵測到疑似硬編碼的 {secret_type}。"
            "硬編碼秘鑰一旦被搜尋引擎或工具掃描到，攻擊者可直接利用，"
            "無需進一步滲透即可存取對應服務。"
        ),
        "remediation": (
            "立即撤銷（revoke）該秘鑰並重新產生。"
            "改用環境變數或密鑰管理服務（Vault、AWS Secrets Manager 等）注入，"
            "確保秘鑰絕不進入版本控制或前端打包產物。"
        ),
        "evidence": evidence,
        "selector": "",
        "bounding_box": None,
        "impact_area": "secret_disclosure",
        "confidence": 0.85,
        "priority_score": 90.0 if severity == "critical" else 75.0,
        "ai_handoff_prompt": (
            "我網站的前端 JS 檔案中偵測到硬編碼秘鑰，請協助分析風險與修復方向：\n"
            f"- 秘鑰類型：{secret_type}\n"
            f"- 偵測位置：{endpoint}\n"
            "請提供：1) 立即應對步驟 2) 長期防範架構建議 3) 如何確認秘鑰未被惡意使用。"
            "不要輸出完整修復程式碼。"
        ),
    }


def _detect_vite_dev_exposure(record: dict[str, Any]) -> dict | None:
    """偵測 Vite/Webpack dev server 原始碼暴露（生產環境誤用 dev server）。"""
    request = record.get("request") or {}
    response = record.get("response") or {}
    endpoint = request.get("endpoint", "")
    status = response.get("status_code")

    if not endpoint or not status:
        return None

    try:
        status_int = int(status)
    except (ValueError, TypeError):
        return None

    if status_int not in range(200, 300):
        return None

    # 檢查 Vite dev server 特徵路徑
    is_vite = any(sig in endpoint for sig in _VITE_DEV_SIGNATURES)
    # 檢查原始 .jsx/.tsx/.vue 暴露
    is_source = any(endpoint.endswith(ext) for ext in _SOURCE_EXT_SIGNATURES)

    if not (is_vite or is_source):
        return None

    evidence = f"Katana 偵測：GET {endpoint} → HTTP {status_int}（應回傳 404）"
    return {
        "category": "security",
        "severity": "critical",
        **_evidence_metadata(
            _rule_id("KATANA_VITE_DEV_EXPOSURE", endpoint),
            evidence,
            "katana_tech_detection",
        ),
        "title": "生產環境暴露 Vite Dev Server 原始碼",
        "description": (
            f"偵測到 {endpoint} 回傳 HTTP {status_int}，"
            "這表示網站在生產環境中執行了 Vite/開發用伺服器，導致完整前端原始碼（.jsx/.tsx、"
            "node_modules 依賴快取）對外公開。攻擊者可直接讀取應用程式邏輯、路由結構、"
            "API 端點，大幅降低逆向工程的難度。"
        ),
        "remediation": (
            "立即將前端改以 `vite build` 打包後部署 `dist/` 目錄，不應在正式環境執行 `vite dev`。"
            "確認 Web Server（Nginx/Cloudflare）只提供 `dist/` 目錄下的靜態檔案，"
            "並封鎖對 `/src/`、`/node_modules/`、`/@vite/`、`/@react-refresh` 等路徑的存取。"
        ),
        "evidence": evidence,
        "selector": "",
        "bounding_box": None,
        "impact_area": "source_code_exposure",
        "confidence": 0.95,
        "priority_score": 95.0,
        "ai_handoff_prompt": (
            "我的網站在生產環境暴露了 Vite dev server 原始碼，請協助分析影響與修復：\n"
            f"- 暴露端點範例：{endpoint}\n"
            "請說明：1) 攻擊者能從原始碼中取得什麼資訊 "
            "2) 正確的生產部署流程 3) 如何確認修復後原始碼不再外洩。"
        ),
    }


def _extract_endpoint_finding(record: dict[str, Any]) -> dict | None:
    """偵測可疑的隱藏 API 端點（非頁面、非靜態資源的路徑）。"""
    request = record.get("request") or {}
    response = record.get("response") or {}
    endpoint = request.get("endpoint", "")
    status = response.get("status_code")
    source = request.get("source", "")

    if not endpoint or not status or not source:
        return None

    # 只看 JS 中解析出來的端點（source 是某個頁面/JS 檔）
    # 排除 source 就是自身的情況（直接爬到）
    if endpoint == source:
        return None

    try:
        status_int = int(status)
    except (ValueError, TypeError):
        return None

    if status_int not in range(200, 300):
        return None

    low = endpoint.lower()

    # 排除靜態資源和已知開發模組
    skip_exts = (".js", ".css", ".png", ".jpg", ".svg", ".woff", ".woff2", ".ico", ".map",
                 ".jsx", ".tsx", ".vue", ".ts")
    skip_prefixes = ("/@vite", "/@react", "/node_modules", "@vite", "@react")

    if any(low.endswith(ext) for ext in skip_exts):
        return None
    if any(p in low for p in skip_prefixes):
        return None

    # 只回報 /api/ 路徑（明確的 API 端點）
    if "/api/" not in low and not low.endswith("/api"):
        return None

    evidence = f"Katana JS 解析：{endpoint} → HTTP {status_int}（來源：{source}）"
    return {
        "category": "security",
        "severity": "medium",
        **_evidence_metadata(
            _rule_id("KATANA_HIDDEN_API_ENDPOINT", f"{endpoint}:{source}"),
            evidence,
            "katana_js_endpoint",
        ),
        "title": f"JS 中發現隱藏 API 端點：{endpoint}",
        "description": (
            f"Katana 從 JavaScript 原始碼中解析出 API 端點 {endpoint}，"
            f"且該端點回應 HTTP {status_int}。此類端點可能未在文件中公開，"
            "若缺乏適當的存取控制，可能成為攻擊面。"
        ),
        "remediation": (
            "確認此端點是否需要對公開網路開放；若否，加上認證中介軟體或 IP 白名單。"
            "建議對所有 API 端點實施統一的認證與授權策略。"
        ),
        "evidence": evidence,
        "selector": "",
        "bounding_box": None,
        "impact_area": "exposed_endpoints",
        "confidence": 0.75,
        "priority_score": 60.0,
        "ai_handoff_prompt": (
            "我網站的 JS 檔案中發現隱藏 API 端點，請協助評估風險：\n"
            f"- 端點：{endpoint}\n"
            f"- HTTP 狀態：{status_int}\n"
            "請說明此類端點的常見攻擊向量與防護方式。"
        ),
    }
