"""跨層資安發現去重：同一個問題被不同偵測層各報一次時只留一筆。

兩種重複都處理（計分前在 `tasks.stage_scoring` 呼叫，被丟的那筆連 DB 列一起刪，
否則同一件事計分扣兩次、報告與問題清單各列一次）：

1. **確定性 ↔ Agent（同端點）**：確定性層（例如 `exposure-file-apidoc` 主動探測）與 Agent 層
   （`agent-observed-security-<雜湊>`）各報同一個 API 文件端點。**只丟掉 Agent 那筆**——
   確定性探測可重現（實際下載到檔案內容當證據），是穩定訊號；其 rule_id 可能涵蓋多個端點
   （v2／v3 api-docs 共用 `exposure-file-apidoc`）刪 DB 列不精準；Agent 的雜湊 rule_id 對應單一
   端點，刪得乾淨。比對只針對確定性層的「敏感檔案外洩」類（exposure，對某 URL「可被公開讀取」
   的判定）：這類端點本身只有「被公開」這一個問題，Agent 對同一 URL 的觀察必然是同一件事，
   以端點路徑比對即可，不需比對弱點類型（Agent 措辭含「未授權」時弱點類型會被歸成 auth，
   與確定性的 exposure 對不上，反而漏併）。

2. **Agent ↔ Agent（同後端資源、不同掛載路徑）**：Next.js rewrite `/api_proxy/* → 後端` 與直連
   `/backend/*` 打到的是**同一個後端資源**，Agent 卻可能各打一次、各報一筆（實測某授權掃描：
   同一個 `visits` 錯誤洩內網 IP，`/api_proxy/visits` 報高、`/backend/visits` 報低，計分扣兩次、
   嚴重度還互相打架）。把反向代理／BFF 的掛載前綴剝掉正規化成同一個資源鍵，**同資源＋同弱點
   類型**的 Agent 發現只留最嚴重那筆（同 `findings.consolidate_security_findings` 的原則：端點相同
   但類型不同＝不同問題、修法不同，不能併）。只併 Agent 層（確定性層身分不動）。

3. **確定性規則 ↔ Agent（跨類別、同一頁同一件事）**：少數問題確定性規則（可重現、綁定頁面）與
   Agent 文字觀察各報一次，但 rule_id 與弱點類型不同，Pass 2 的「同資源＋同 vuln_class」配不起來
   （實測 `/management/login` 密碼欄 `type="text"`：form_scanner 報 `form-password-unmasked`、Agent
   另報一筆，Agent 的 vuln_class 落在 other）。以 `_BRIDGE_CONCEPTS` 列舉實際會重疊的少數組合
   （確定性 rule_id → 能認出等義 Agent 觀察的關鍵字群，每群任一命中、各群都要命中才算），同一頁
   （canonical resource）同時出現時**保留確定性那筆、丟掉 Agent**（確定性可重現、措辭穩定）。
   只丟 Agent，且必須有對應的確定性發現在同一頁，才會併——避免誤丟 Agent 獨有的觀察。
"""

from __future__ import annotations

# 反向代理／BFF／API 閘道常見的掛載前綴（通用命名慣例，非任何目標特定路徑；與
# katana_scanner._API_ENDPOINT_HINT 同精神）。`/api_proxy/x` 與 `/backend/x` 剝掉前綴後
# 都是同一個後端資源 `/x`。只剝開頭一段、且後面要還有資源，裸 `/api` 不剝。
_MOUNT_SEGMENTS = frozenset(
    {"api", "api_proxy", "apiproxy", "backend", "bff", "gateway", "proxy", "rest"}
)

# Pass 3 跨類別橋接：確定性 rule_id → 能認出等義 Agent 觀察的關鍵字群。每個元組是一群
# 同義詞（任一命中即算這群命中），一筆 Agent 發現要「每一群都命中」才視為同一件事。
# 只列實際會重疊的少數組合，刻意保守避免誤丟 Agent 獨有觀察。
_BRIDGE_CONCEPTS: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = (
    # 密碼欄位明文：form_scanner 的 form-password-unmasked ↔ Agent 觀察到密碼欄 type="text"
    (
        "form-password-unmasked",
        (
            ("密碼", "password"),  # 是密碼欄
            ('type="text"', "type=text", "明碼", "明文", "遮蔽", "遮罩", "mask", "plaintext"),
        ),
    ),
)


def _is_exposure(finding: dict) -> bool:
    """確定性層的敏感檔案外洩類發現（某個 URL 可被公開讀取）。"""
    rule_id = str(finding.get("rule_id") or "")
    return (
        rule_id.startswith("exposure-")
        or finding.get("evidence_source") == "exposure_probe"
        or finding.get("impact_area") == "information_exposure"
    )


def _endpoint_of(finding: dict) -> str:
    """發現對應的端點路徑：exposure 存在 `endpoint`、Agent 存在 `observed_endpoint`。"""
    evidence_json = finding.get("evidence_json") or {}
    return str(evidence_json.get("endpoint") or evidence_json.get("observed_endpoint") or "")


def _resource_of(finding: dict) -> str:
    """資源路徑：優先 endpoint／observed_endpoint，其次 `evidence_json.url`（頁面類確定性
    規則如 form-password-unmasked 把頁面網址存在 url）。"""
    endpoint = _endpoint_of(finding)
    if endpoint:
        return endpoint
    return str((finding.get("evidence_json") or {}).get("url") or "")


def _canonical_resource(path: str) -> str:
    """剝掉反向代理／BFF 掛載前綴，把同一後端資源的不同掛載路徑正規化成同一個鍵。

    只剝開頭一段通用掛載詞、且後面要還有資源段（裸 `/api`／`/backend` 不剝）；非掛載詞
    （`/shop/...`）原樣保留。沿用 Agent 的 `endpoint_path`（小寫、去查詢字串與尾斜線）。
    """
    from apps.agent.findings import endpoint_path

    norm = endpoint_path(path)
    if not norm or norm == "/":
        return norm
    segments = norm.strip("/").split("/")
    if len(segments) >= 2 and segments[0] in _MOUNT_SEGMENTS:
        return "/" + "/".join(segments[1:])
    return norm


def consolidate_cross_layer(findings: list[dict]) -> tuple[list[dict], list[dict]]:
    """回傳（保留的發現, 被丟掉的 Agent 發現）。

    先做確定性 ↔ Agent 同端點併除，再做 Agent ↔ Agent 同後端資源併除；沒有端點資訊的
    發現（站台層級、無 URL）一律保留，不會被誤併。
    """
    from apps.agent.findings import is_agent_security_rule, rank, vuln_class

    # Pass 1：確定性 exposure 已有同端點 → 丟掉 Agent 那筆
    exposed_endpoints: set[str] = set()
    for finding in findings:
        if finding.get("category") != "security":
            continue
        if is_agent_security_rule(finding.get("rule_id")) or not _is_exposure(finding):
            continue
        endpoint = _endpoint_of(finding)
        if endpoint:
            exposed_endpoints.add(endpoint)

    dropped: list[dict] = []
    survivors: list[dict] = []
    for finding in findings:
        if (
            finding.get("category") == "security"
            and is_agent_security_rule(finding.get("rule_id"))
            and _endpoint_of(finding)
            and _endpoint_of(finding) in exposed_endpoints
        ):
            dropped.append(finding)
            continue
        survivors.append(finding)

    # Pass 2：Agent ↔ Agent 同後端資源＋同弱點類型 → 只留最嚴重那筆
    kept: list[dict] = []
    best_index_by_key: dict[tuple[str, str], int] = {}
    for finding in survivors:
        if not (
            finding.get("category") == "security"
            and is_agent_security_rule(finding.get("rule_id"))
        ):
            kept.append(finding)
            continue
        resource = _canonical_resource(_endpoint_of(finding))
        if not resource or resource == "/":
            kept.append(finding)
            continue
        key = (resource, vuln_class(finding.get("title", ""), finding.get("description", "")))
        incumbent = best_index_by_key.get(key)
        if incumbent is None:
            best_index_by_key[key] = len(kept)
            kept.append(finding)
        elif rank(finding) < rank(kept[incumbent]):
            dropped.append(kept[incumbent])
            kept[incumbent] = finding
        else:
            dropped.append(finding)

    # Pass 3：確定性規則 ↔ Agent 跨類別橋接 → 保留確定性、丟 Agent
    # 先找出每個橋接概念在確定性層已覆蓋的資源（canonical）
    bridged: dict[str, set[str]] = {}
    for finding in kept:
        if finding.get("category") != "security":
            continue
        rule_id = str(finding.get("rule_id") or "")
        for det_rule, _groups in _BRIDGE_CONCEPTS:
            if rule_id == det_rule:
                resource = _canonical_resource(_resource_of(finding))
                if resource and resource != "/":
                    bridged.setdefault(det_rule, set()).add(resource)
    if not bridged:
        return kept, dropped

    final: list[dict] = []
    for finding in kept:
        if finding.get("category") == "security" and is_agent_security_rule(
            finding.get("rule_id")
        ):
            resource = _canonical_resource(_resource_of(finding))
            text = f"{finding.get('title', '')} {finding.get('description', '')}".lower()
            bridged_away = any(
                resource in bridged.get(det_rule, ())
                and all(any(kw in text for kw in group) for group in groups)
                for det_rule, groups in _BRIDGE_CONCEPTS
            )
            if bridged_away:
                dropped.append(finding)
                continue
        final.append(finding)
    return final, dropped
