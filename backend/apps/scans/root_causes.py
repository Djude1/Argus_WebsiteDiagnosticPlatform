"""根本原因關聯（roadmap「跨領域工程化」Root Cause Correlation）。

把「在同一個地方修」的問題歸到同一個根本原因，讓網站主知道改一處設定能一次解決幾個問題。
例如 CSP、HSTS、X-Frame-Options 都是網站伺服器（或反向代理、CDN）的回應標頭設定，
SEO 的「圖片缺少 alt」與 axe-core 的 image-alt 是同一件事。

只是呈現上的分組：不改嚴重度、不合併問題、不影響計分與歷史比較。
只收修法確實在同一處的規則；只有一個問題的根本原因不分組（分組沒有意義）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


@dataclass(frozen=True)
class RootCause:
    id: str
    title: str
    where: str  # 在哪裡修
    summary: str
    pattern: re.Pattern

    def matches(self, rule_id: str) -> bool:
        return bool(rule_id) and bool(self.pattern.search(rule_id))


ROOT_CAUSES: tuple[RootCause, ...] = (
    RootCause(
        "server-headers",
        "網站伺服器的回應標頭設定",
        "網站伺服器（Nginx、Apache、IIS）、反向代理或 CDN 的回應標頭設定",
        "這些問題都是在網站回應中加上或移除標頭，修法在同一個設定檔：改一次，所有頁面同時生效。",
        # 逐頁檢查的標頭規則名稱由標題產生（SECURITY_CSP_…），站台層級的是 header-…
        re.compile(
            r"^(SECURITY_(CSP|HSTS|X_FRAME_OPTIONS|X_CONTENT_TYPE_OPTIONS|REFERRER_POLICY|"
            r"PERMISSIONS_POLICY)_|header-)"
        ),
    ),
    RootCause(
        "cookie-attributes",
        "Cookie 的安全屬性",
        "後端程式或框架設定 Cookie 的地方（Session 設定）",
        "Secure、HttpOnly、SameSite 都在網站發出 Cookie 時一起設定，通常是框架的 Session 設定。",
        re.compile(r"^cookie-"),
    ),
    RootCause(
        "tls",
        "HTTPS 憑證與加密設定",
        "網站伺服器或 CDN 的 TLS 設定",
        "憑證與加密協定在同一處設定；使用 CDN 時多半由 CDN 後台調整。",
        re.compile(r"^ssl-"),
    ),
    RootCause(
        "email-domain-auth",
        "網域的寄件驗證紀錄（SPF／DMARC）",
        "網域的 DNS 設定",
        "SPF 與 DMARC 都是網域 DNS 裡的 TXT 紀錄，在 DNS 管理介面一起設定，防止他人冒用網域寄信。",
        re.compile(r"^dns-(spf|dmarc)-"),
    ),
    RootCause(
        "image-alt",
        "圖片缺少替代文字",
        "網站內容管理介面或頁面範本的 <img> 標籤",
        "SEO 檢查與無障礙檢查（axe-core）看的是同一件事：圖片要有描述內容的 alt 文字。",
        re.compile(r"^(SEO_ALT_|axe-(image-alt|input-image-alt|role-img-alt|svg-img-alt|area-alt)$)"),
    ),
    RootCause(
        "article-metadata",
        "文章頁的作者與日期標記",
        "文章頁範本（佈景主題）輸出的 meta 與 JSON-LD",
        "作者與發布、更新日期都由文章範本輸出，修好範本後所有文章一起生效。",
        re.compile(r"^geo-article-"),
    ),
)


def cause_for(rule_id: str) -> RootCause | None:
    return next((cause for cause in ROOT_CAUSES if cause.matches(rule_id or "")), None)


def annotate_root_causes(issues: list[dict]) -> list[dict]:
    """替問題加上 ``root_cause``（同一根本原因有 2 個以上問題才加），回傳根本原因摘要。

    摘要依最高嚴重度、問題數、受影響頁數排序：``id``、``title``、``where``、``summary``、
    ``issues``（問題 key）、``count``、``severity``（最高）、``pages``（受影響頁數的最大值，
    同一批頁面多半重複，不相加）。
    """
    members: dict[str, list[dict]] = {}
    for issue in issues:
        cause = cause_for(issue.get("rule_id") or "")
        if cause:
            members.setdefault(cause.id, []).append(issue)
    summaries = []
    for cause in ROOT_CAUSES:
        group = members.get(cause.id) or []
        if len(group) < 2:
            continue
        for issue in group:
            issue["root_cause"] = cause.id
        summaries.append({
            "id": cause.id,
            "title": cause.title,
            "where": cause.where,
            "summary": cause.summary,
            "issues": [issue["key"] for issue in group],
            "count": len(group),
            "severity": min(
                (issue["severity"] for issue in group), key=lambda s: _SEVERITY_RANK.get(s, 9)
            ),
            "pages": max(issue.get("pages", 0) for issue in group),
        })
    summaries.sort(
        key=lambda s: (_SEVERITY_RANK.get(s["severity"], 9), -s["count"], -s["pages"])
    )
    return summaries
