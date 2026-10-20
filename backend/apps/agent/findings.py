"""把 Hermes-Agent 的 report_ux_issue 結果落地成 Finding。

設計：
- loop 層只負責收集 issues（dict 列表），不直接寫 DB；落地分離方便測試。
- 落地時依 issue['url'] 找對應 Page（若找不到則 page=None，視為站台層級 finding）。
- ai_handoff_prompt 走專案統一模板，明確要求對方 LLM「不要輸出完整修復程式碼」。
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from difflib import SequenceMatcher
from urllib.parse import urlsplit

from apps.scans.models import Finding, Page, ScanJob

# Agent 資安觀察的規則代號前綴。2026-10-16 前所有回報共用 "agent-observed-security" 這一個代號，
# 計分、優先處理、報告與歷史比較都以代號判斷「同一個問題」，於是一次掃描只有第一筆會被計分；
# 實測站台 實測「嚴重」的 Swagger 外洩因此被同主題的「中」那筆擋掉、沒進優先處理。
AGENT_SECURITY_RULE = "agent-observed-security"

# 弱點類型：同一端點、同一類型才算同一個問題（端點相同但一個是 SQL 注入、一個是缺頻率限制，
# 修法不同，不能合併）。依序比對，第一個命中者勝出。
_VULN_CLASSES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sqli", ("sql injection", "sql 注入", "sqli", "sqlmap")),
    ("xss", ("xss", "跨站腳本", "cross-site scripting")),
    ("injection", ("注入", "injection", "ssti", "xxe", "command execution", "指令執行")),
    ("ssrf", ("ssrf", "伺服器端請求偽造")),
    ("redirect", ("open redirect", "開放轉址", "開放重新導向")),
    ("upload", ("上傳", "upload")),
    ("jwt", ("jwt", "token 偽造", "簽章")),
    ("idor", ("idor", "越權", "水平權限", "他人資料", "broken object")),
    ("auth", ("未授權", "未登入", "認證", "驗證繞過", "unauthorized", "unauthenticated",
              "authentication", "暴力", "brute", "密碼重設", "帳號接管")),
    ("csrf", ("csrf", "跨站請求偽造")),
    ("cors", ("cors",)),
    ("exposure", ("外洩", "洩漏", "暴露", "曝露", "公開", "exposure", "disclosure", "leak",
                  "swagger", "openapi", "api-docs", "堆疊", "stack trace", "debug")),
)

# 公開的索引檔：本來就要給所有人讀，列出登入頁也不算弱點（登入頁本身就公開）。
_PUBLIC_INDEX_FILE = re.compile(r"^/(robots\.txt|sitemap[\w.-]*\.xml(\.gz)?)$", re.I)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
# 標題相似到這個程度、而且同一類型，就視為同一個問題換句話說
_TITLE_SIMILARITY = 0.6


def endpoint_path(url: str) -> str:
    """回報網址的路徑（小寫、去掉查詢字串與結尾斜線）。

    Agent 偶爾寫成「網址 (or …)」，只取第一段。
    """
    raw = (url or "").strip().split()[0] if (url or "").strip() else ""
    if not raw:
        return ""
    path = urlsplit(raw).path if "://" in raw else raw.split("?", 1)[0]
    path = path.lower().rstrip("/")
    return path or "/"


def is_public_index_file(url: str) -> bool:
    return bool(_PUBLIC_INDEX_FILE.match(endpoint_path(url)))


def vuln_class(title: str, description: str = "") -> str:
    text = f"{title} {description}".lower()
    for name, keywords in _VULN_CLASSES:
        if any(keyword in text for keyword in keywords):
            return name
    return "other"


def agent_security_rule_id(title: str, description: str, url: str) -> str:
    """每個 Agent 資安觀察自己的規則代號：弱點類型＋端點路徑（沒有端點時用標題）。

    不把標題放進有端點時的雜湊：同一個問題每次掃描的措辭都不同，換掉一個字就會變成
    「新問題」，歷史比較就失去意義。
    """
    cls = vuln_class(title, description)
    anchor = endpoint_path(url) or _normalize_title(title)
    digest = hashlib.sha1(f"{cls}|{anchor}".encode()).hexdigest()[:10]
    return f"{AGENT_SECURITY_RULE}-{digest}"


def is_agent_security_rule(rule_id: str | None) -> bool:
    return (rule_id or "").startswith(AGENT_SECURITY_RULE)


_EXCERPT_SIMILARITY = 0.9


def _normalize_title(title: str) -> str:
    return re.sub(r"[\W_]+", "", (title or "").lower())


def _normalize_excerpt(finding: dict) -> str:
    """證據片段去掉數字（時間戳、流水號）與空白，留下回應的「形狀」。"""
    evidence_json = finding.get("evidence_json") or {}
    excerpt = str(evidence_json.get("excerpt") or finding.get("evidence") or "")
    return re.sub(r"[\d\s]+", "", excerpt.lower())[:600]


def same_issue(a: dict, b: dict) -> bool:
    if a.get("rule_id") == b.get("rule_id"):
        return True
    if vuln_class(a.get("title", ""), a.get("description", "")) != vuln_class(
        b.get("title", ""), b.get("description", "")
    ):
        return False
    ratio = SequenceMatcher(
        None, _normalize_title(a.get("title", "")), _normalize_title(b.get("title", ""))
    ).ratio()
    if ratio >= _TITLE_SIMILARITY:
        return True
    # 同類型、不同端點，但擷取到的回應幾乎一樣（同一個 WAF 攔截頁從 /.git/HEAD 與 /.env 各觸發
    # 一次，只差時間戳）＝同一件事（2026-10-19 實掃報告 4.1／4.2 列了兩次）
    excerpt_a, excerpt_b = _normalize_excerpt(a), _normalize_excerpt(b)
    if len(excerpt_a) < 40 or len(excerpt_b) < 40:
        return False
    return SequenceMatcher(None, excerpt_a, excerpt_b).ratio() >= _EXCERPT_SIMILARITY


def rank(finding: dict) -> tuple[int, int]:
    """越小越該保留：嚴重度高、已用工具驗證的優先。"""
    evidence_json = finding.get("evidence_json") or {}
    return (
        _SEVERITY_ORDER.get(finding.get("severity", "low"), 9),
        0 if evidence_json.get("tool_verified") else 1,
    )


def consolidate_security_findings(findings: Iterable[dict]) -> list[dict]:
    """同一次掃描裡，不同專家對同一個問題的多次回報合併成一筆。

    同一個問題＝規則代號相同（同類型＋同端點），或同類型且標題相近。保留最嚴重、
    已驗證的那筆，其餘併入（`evidence_json.merged_reports` 記合併了幾次回報）。
    非 Agent 觀察（例如 sqlmap 確認的注入）原樣保留。
    """
    kept: list[dict] = []
    for finding in findings:
        if not is_agent_security_rule(finding.get("rule_id")):
            kept.append(finding)
            continue
        match = next(
            (
                idx
                for idx, existing in enumerate(kept)
                if is_agent_security_rule(existing.get("rule_id"))
                and same_issue(existing, finding)
            ),
            None,
        )
        if match is None:
            kept.append(finding)
            continue
        existing = kept[match]
        merged = 1 + int((existing.get("evidence_json") or {}).get("merged_reports", 1))
        winner = finding if rank(finding) < rank(existing) else existing
        winner = dict(winner)
        winner["evidence_json"] = {**(winner.get("evidence_json") or {}), "merged_reports": merged}
        kept[match] = winner
    return kept

UX_HANDOFF_TEMPLATE = """我網站有以下 UX 問題，請協助我分析並提供修復方向：
- 問題類型: ux
- 嚴重度: {severity}
- 問題描述: {description}
- 對應位置: {url}
- 元素 selector: {selector}
- 修補建議方向: {remediation}

請依此資訊提供具體修改方向、檢查步驟與注意事項；不要輸出完整修復程式碼。"""


VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}

# AI 擬真使用者回報的 UX 問題最高中風險（2026-10-10 MiniMax 實測）：Agent 曾把
# 「加入購物車導向聯絡表單」判成嚴重，和「SSL 憑證已過期」同級、UX 分數 41→23。
# 流程問題會讓使用者卡住，但不會讓網站被入侵或資料外洩；與資安 Agent 觀察的報告上限一致。
UX_SEVERITY_CAP = "medium"


def cap_ux_severity(severity: str | None, blocking: bool = False) -> str:
    """Agent UX 問題的嚴重度：未知值當 low，critical／high 降為 medium。

    `blocking`＝核心任務被完全卡死、根本無法完成（例如登入頁無法輸入或送出、結帳送不出去），
    不是繞得過去的困擾：允許升到 **high**（仍封頂 high，不給 critical——UX 觀察不應到最高級）。
    一般卡住、流程不順仍維持 medium 上限（2026-10-20，1D47 報告「登入頁完全壞掉」只給中風險偏輕）。
    """
    if severity not in VALID_SEVERITIES:
        return "low"
    if blocking and severity in ("critical", "high", "medium"):
        return "high"
    return UX_SEVERITY_CAP if severity in ("critical", "high") else severity


def persist_agent_issues(
    scan_job: ScanJob, issues: Iterable[dict], default_priority: float = 50.0
) -> list[Finding]:
    """把 agent 收集的 issue 落地成 Finding（category=ux）。

    回傳新建的 Finding 物件列表。同 scan_job 內若已有相同 title 的 ux finding，
    則略過（避免 agent 多輪重複回報同一問題）。
    """
    created: list[Finding] = []
    existing_titles = set(
        scan_job.findings.filter(category=Finding.Category.UX).values_list("title", flat=True)
    )

    page_cache: dict[str, Page | None] = {}

    for issue in issues:
        title = (issue.get("title") or "").strip()[:255]
        if not title or title in existing_titles:
            continue

        severity = cap_ux_severity(issue.get("severity"), blocking=bool(issue.get("blocking")))

        description = (issue.get("description") or "").strip()
        if not description:
            continue

        remediation = (issue.get("remediation") or "請檢視該流程的可用性並對齊使用者預期。").strip()
        url = (issue.get("url") or "").strip()
        selector = (issue.get("selector") or "").strip()[:512]

        page = _resolve_page(scan_job, url, page_cache)
        evidence = f"URL: {url}\nselector: {selector}"
        rule_id = f"AGENT_UX_{hashlib.sha1(title.encode('utf-8')).hexdigest()[:10].upper()}"

        handoff = UX_HANDOFF_TEMPLATE.format(
            severity=severity,
            description=description,
            url=url or "(站台層級)",
            selector=selector or "(無)",
            remediation=remediation,
        )

        finding = Finding.objects.create(
            scan_job=scan_job,
            page=page,
            category=Finding.Category.UX,
            severity=severity,
            title=title,
            description=description,
            remediation=remediation,
            evidence=evidence,
            rule_id=rule_id,
            evidence_type="agent_observation",
            evidence_json={
                "type": "agent_observation",
                "source": "hermes_agent",
                "excerpt": evidence,
                "url": url,
                "selector": selector,
            },
            evidence_source="hermes_agent",
            ai_explanation="",
            ai_remediation="",
            llm_model="",
            llm_generated_at=None,
            selector=selector,
            ai_handoff_prompt=handoff,
            priority_score=default_priority,
            impact_area="ux",
            confidence=0.7,  # Agent 自我回報，預設信心略低於規則式掃描
        )
        created.append(finding)
        existing_titles.add(title)

    return created


def persist_agent_security_findings(
    scan_job: ScanJob, findings: Iterable[dict]
) -> list[Finding]:
    """把 Hermes-Agent 主動驗證（probe_sql_injection）確認的 security finding 落地。

    - findings 為 `scanners.make_finding` 產生的 dict（欄位對應 Finding model）。
    - 套 `owasp_mapper.tag` 補 OWASP/CWE，使與 pipeline 的 kali finding 標籤一致。
    - 先以 `consolidate_security_findings` 合併同一個問題的多次回報；sqlmap 結果依 description
      去重（description 內含具體 URL），避免 agent 多輪對同一 URL 重複記錄。
    - 任一筆失敗只跳過該筆，不影響其他（silent-fail），不讓 agent 例外拖垮掃描。
    """
    from apps.scans.security import owasp_mapper

    created: list[Finding] = []
    seen = set(
        scan_job.findings.filter(rule_id="kali-sqlmap-sqli").values_list(
            "description", flat=True
        )
    )
    # 已落地的 Agent 觀察代號：同一個問題不重複寫入（正常只會呼叫一次，防重複呼叫）
    seen_rules = set(
        scan_job.findings.filter(rule_id__startswith=AGENT_SECURITY_RULE).values_list(
            "rule_id", flat=True
        )
    )
    for raw in consolidate_security_findings(findings):
        if is_agent_security_rule(raw.get("rule_id")) and raw.get("rule_id") in seen_rules:
            continue
        try:
            tagged = owasp_mapper.tag(dict(raw))
            desc = tagged.get("description", "")
            if not desc or desc in seen:
                continue
            obj = Finding.objects.create(scan_job=scan_job, page=None, **tagged)
            created.append(obj)
            seen.add(desc)
            seen_rules.add(obj.rule_id)
        except Exception:  # noqa: BLE001 — 單筆落地失敗不影響其他 finding 與主掃描
            continue
    return created


def _resolve_page(scan_job: ScanJob, url: str, cache: dict[str, Page | None]) -> Page | None:
    if not url:
        return None
    if url in cache:
        return cache[url]
    page = scan_job.pages.filter(final_url=url).first() or scan_job.pages.filter(url=url).first()
    cache[url] = page
    return page
