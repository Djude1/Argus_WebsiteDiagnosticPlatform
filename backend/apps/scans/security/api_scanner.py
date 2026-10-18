"""被動 API 檢查（2026-10-11，回應評審「能否對後端 API 檢測」）。

只分析爬取期間瀏覽器**自己發出**的同網站 XHR／fetch 回應摘要（crawler `_observe_api_response`），
不發任何新請求、不讀後端原始碼：
- `api-error-stack-trace`（中）：API 錯誤回應洩漏堆疊追蹤或框架除錯資訊（CWE-209，
  OWASP Top 10:2025 A10 例外狀況處理不當）
- `api-cors-wildcard`（低）：回傳 JSON 的 API 允許任何網站跨域讀取（Access-Control-Allow-Origin: *）

另整理「API 端點清單」（只存方法、路徑、狀態碼、內容類型與命中的規則，不存查詢字串與回應內容），
存 `ScanJob.warning_summary["api_surface"]`，資安分析頁顯示。
"""

from __future__ import annotations

import re

from apps.scans.scanners import make_finding
from apps.scans.security.redaction import redact_pii_in_text
from apps.scans.security.secret_scanner import redact_secrets_in_text

MAX_SURFACE_ENDPOINTS = 50
_EXCERPT_CHARS = 240

# 各框架／語言的堆疊追蹤與除錯頁特徵；只認結構性字樣，避免把一般錯誤訊息當成洩漏
_STACK_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("Python", re.compile(r"Traceback \(most recent call last\)")),
    ("Django", re.compile(r"You're seeing this error because you have <code>DEBUG = True")),
    ("Java", re.compile(r"\n\s*at [\w$.]+\([\w$]+\.java:\d+\)")),
    (".NET", re.compile(r"\n\s*at [\w.`<>]+\(.*\) in .+:line \d+")),
    ("Node.js", re.compile(r"\n\s*at .+ \((?:/|[A-Za-z]:\\)[^)]+\.(?:js|ts|mjs|cjs):\d+:\d+\)")),
    ("PHP", re.compile(
        r"(?:Fatal error|Uncaught \w+Exception).{0,200} in /\S+\.php(?: on line |:)\d+"
    )),
    ("Ruby", re.compile(r"/\S+\.rb:\d+:in `")),
    ("SQL", re.compile(r"SQLSTATE\[\w+\]|You have an error in your SQL syntax|ORA-\d{5}")),
)


def _stack_kind(body: str) -> tuple[str, str]:
    """回傳 (框架名稱, 命中附近的片段)；沒命中回 ("", "")。"""
    for name, pattern in _STACK_PATTERNS:
        match = pattern.search(body or "")
        if match:
            start = max(0, match.start() - 40)
            return name, body[start:start + _EXCERPT_CHARS]
    return "", ""


def _excerpt(text: str) -> str:
    """證據片段：壓成一行、遮罩個資與金鑰。"""
    flat = " ".join((text or "").split())
    return redact_secrets_in_text(redact_pii_in_text(flat))[:_EXCERPT_CHARS]


def _is_json(observation: dict) -> bool:
    return "json" in (observation.get("headers") or {}).get("content-type", "").lower()


def analyze_api(observations: list[dict], origin: str = "") -> tuple[list[dict], dict]:
    """回傳 (findings, api_surface)。任何例外由呼叫端處理。"""
    leaks: list[tuple[dict, str, str]] = []
    wildcard: list[dict] = []
    surface_rows: list[dict] = []
    for obs in observations or []:
        rules: list[str] = []
        kind, snippet = _stack_kind(obs.get("error_body", ""))
        if kind:
            leaks.append((obs, kind, snippet))
            rules.append("api-error-stack-trace")
        headers = obs.get("headers") or {}
        if _is_json(obs) and headers.get("access-control-allow-origin", "").strip() == "*":
            wildcard.append(obs)
            rules.append("api-cors-wildcard")
        surface_rows.append({
            "method": obs.get("method", "GET"),
            "path": obs.get("path", "/"),
            "status": obs.get("status"),
            "content_type": headers.get("content-type", "").split(";")[0].strip(),
            "rules": rules,
        })

    findings: list[dict] = []
    if leaks:
        lines = [
            f"{obs['method']} {obs['path']} → HTTP {obs.get('status')}（{kind}）："
            f"{_excerpt(snippet)}"
            for obs, kind, snippet in leaks[:5]
        ]
        findings.append(make_finding(
            category="security", severity="medium", rule_id="api-error-stack-trace",
            title="API 錯誤回應洩漏堆疊追蹤或除錯資訊",
            description=(
                f"網站前端呼叫的 {len(leaks)} 個 API 在出錯時，"
                "把程式的堆疊追蹤或除錯資訊直接回傳給瀏覽器"
                "（例如檔案路徑、程式行號、資料庫錯誤）。攻擊者可藉此得知後端架構與程式位置，"
                "加速找出可利用的弱點。"
            ),
            remediation=(
                "正式環境關閉除錯模式（如 Django DEBUG=False、PHP display_errors=Off），"
                "API 出錯時只回傳通用訊息與錯誤代碼，詳細堆疊寫進伺服器日誌。"
            ),
            evidence="\n".join(lines),
            impact_area="vulnerability",
            evidence_type="api_response",
            evidence_json={
                "endpoints": [
                    {"method": o["method"], "path": o["path"], "status": o.get("status"), "kind": k}
                    for o, k, _ in leaks[:20]
                ],
                "total": len(leaks),
            },
            evidence_source="passive_api",
        ))
    if wildcard:
        paths = [f"{o['method']} {o['path']}" for o in wildcard[:10]]
        findings.append(make_finding(
            category="security", severity="low", rule_id="api-cors-wildcard",
            title="API 允許任何網站跨域讀取",
            description=(
                f"{len(wildcard)} 個回傳 JSON 的 API 設定 Access-Control-Allow-Origin: *，"
                "任何網站的程式都能讀取這些回應。公開資料可以接受；"
                "若 API 會回傳需要登入或內部才能看的資料，就應限制來源。"
            ),
            remediation=(
                "確認這些 API 是否只提供公開資料；不是的話改成只允許自己的網域"
                "（例如 Access-Control-Allow-Origin: " + (origin or "https://你的網域") + "）。"
            ),
            evidence="\n".join(paths),
            impact_area="vulnerability",
            evidence_type="api_response",
            evidence_json={"endpoints": paths, "total": len(wildcard)},
            evidence_source="passive_api",
        ))

    surface = {
        "total": len(surface_rows),
        "with_issues": sum(1 for r in surface_rows if r["rules"]),
        # 有問題的排前面，其餘依路徑
        "endpoints": sorted(surface_rows, key=lambda r: (not r["rules"], r["path"], r["method"]))[
            :MAX_SURFACE_ENDPOINTS
        ],
    }
    return findings, surface
