"""Finding 跨掃描正典身分（ADR-0006 決策 A）。

兩層（確定性＋AI Agent）共用一把跨掃描鍵：**正規化資源 ＋ 穩定弱點類別**。取代
`coverage.issue_key` 的 `rule_id or "category:title"`——Agent 觀察的雜湊 `rule_id` 會隨措辭／
觀察端點微調而漂、確定性 `rule_id` 又不含端點（同一條規則打到不同端點會被當成同一筆）。

ADR 落地順序第 1 刀：先建立本函式並與舊鍵**並存**（coverage 兩種都寫），第 2 刀才把歷史比較
切換過來。純函式、不碰 DB、不碰 ScanJob.status。
"""

from __future__ import annotations

import re

# 數字路徑段（或數字起頭帶尾綴，如 1043-117736）換成 '#'：讓 /api/users/1 與 /api/users/2
# 得到同一個資源鍵（IDOR 枚舉同一端點的不同物件 id 是同一件事）。
_NUMERIC_SEGMENT = re.compile(r"^\d[\w.\-]*$")


def canonical_resource(path: str) -> str:
    """資源路徑正規化成跨掃描穩定的鍵。

    小寫、去查詢字串與尾斜線（`agent.findings.endpoint_path`）、剝反向代理／BFF 掛載前綴
    （`cross_layer._MOUNT_SEGMENTS`，`/api_proxy/x` 與 `/backend/x` → `/x`）、數字路徑段換 '#'。
    沒有路徑或只有根路徑時原樣回傳（空字串＝站台層級）。
    """
    from apps.agent.findings import endpoint_path
    from apps.scans.security.cross_layer import _MOUNT_SEGMENTS

    norm = endpoint_path(path)
    if not norm or norm == "/":
        return norm
    segments = norm.strip("/").split("/")
    if len(segments) >= 2 and segments[0] in _MOUNT_SEGMENTS:
        segments = segments[1:]
    segments = ["#" if _NUMERIC_SEGMENT.match(seg) else seg for seg in segments]
    return "/" + "/".join(segments)


def resource_of(finding: dict) -> str:
    """發現對應的正規化資源：endpoint／observed_endpoint 優先，其次 `evidence_json.url`
    （頁面類確定性規則如 form-password-unmasked 把頁面網址存在 url）。無則回空字串。"""
    evidence_json = finding.get("evidence_json") or {}
    raw = (
        evidence_json.get("endpoint")
        or evidence_json.get("observed_endpoint")
        or evidence_json.get("url")
        or ""
    )
    return canonical_resource(str(raw))


def finding_identity(finding: dict) -> str:
    """跨掃描正典鍵。

    資安發現：``<弱點類別>|<資源>|<owasp>|<cwe>``（資源空＝``site``）。同一個洞不論被確定性
    規則還是 Agent 打到、不論措辭或掛載前綴如何，都收斂成同一鍵；端點相同但弱點類型不同
    （SQL 注入 vs 缺頻率限制）仍是不同鍵（弱點類別不同）。

    非資安發現：沿用舊的穩定身分（規則代號，或「分類:標題」），這些層的 `rule_id` 本就穩定，
    不需要重算。
    """
    category = finding.get("category") or ""
    if category != "security":
        rule_id = finding.get("rule_id")
        return rule_id or f"{category}:{finding.get('title', '')}"

    from apps.agent.findings import vuln_class

    resource = resource_of(finding) or "site"
    cls = vuln_class(finding.get("title", ""), finding.get("description", ""))
    owasp = (finding.get("owasp_category") or "").strip().upper()
    cwe = (finding.get("cwe_id") or "").strip().upper()
    key = f"{cls}|{resource}|{owasp}|{cwe}"
    # 無資源、無類別、無標籤的站台層級資安問題：退回附標題，避免把無關問題併成一筆
    # （ADR-0006 風險「正典鍵過度合併」的保守防線）。
    if cls == "other" and resource == "site" and not owasp and not cwe:
        key = f"{key}|{(finding.get('title') or '').strip().lower()}"
    return key
