# SRI 缺失偵測 + DNS/郵件安全掃描器（被動廣度補強）

**日期**：2026-06-13  
**操作者**：Claude

## 變更內容

- **新增 `backend/apps/scans/security/sri_scanner.py`**
  - `analyze_sri(pages)` 解析 crawled_pages HTML，偵測外部跨來源 `<script>`/`<link>` 缺少 `integrity` 屬性
  - 使用 stdlib `html.parser.HTMLParser`，不引入 BeautifulSoup
  - 同一 CDN URL 去重，整個 scan 只報一次；severity 一律 LOW
- **新增 `backend/apps/scans/security/dns_scanner.py`**
  - `analyze_dns(host)` 用 dnspython 查詢 SPF / DMARC / DNSSEC
  - SPF 缺失 → MEDIUM；SPF `+all`（過寬授權）→ HIGH
  - DMARC 缺失 / `p=none` → LOW；DNSSEC 缺失 → LOW
  - 查不到時退父網域一層；不做 DKIM（黑盒無法可靠列舉 selector）；例外 silent-fail 回 `[]`
- **更新 `backend/apps/scans/security/owasp_mapper.py`**
  - 新增 6 個 rule_id 對映，含首次使用的 A08（軟體與資料完整性失效，對應 SRI）
  - DNS 類 rule_id 對映至 A05（安全設定錯誤）
- **更新 `backend/apps/scans/tasks.py`**
  - `deep_security_findings()` 函式依序呼叫 `analyze_sri(crawled_pages)` 與 `analyze_dns(host)`
  - findings 由 tasks.py 統一寫入 DB（符合職責分離原則）
- **新增相依 `dnspython`**（`uv add dnspython`，已寫入 `pyproject.toml`）

## 原因

補齊 Nessus 差距分析文件中的兩個 gap：

- **Gap #4 SRI 缺失**（`docs/nessus-gap-analysis.md` 完全缺少 #4）：外部 CDN 資源缺 `integrity` hash 可被 CDN 供應商或中間人竄改（OWASP A08）
- **Gap #7 DNS/郵件安全**（完全缺少 #7）：SPF/DMARC 缺失讓攻擊者可假冒網域發送釣魚郵件，DNSSEC 缺失有 DNS 欺騙風險

兩項均屬純加法廣度補強，不改現有掃描邏輯，提升報告對 Nessus 的競爭力。

## 影響範圍

- **純加法，silent-fail 設計**：任一 scanner 例外均回傳 `[]`，不影響主掃描流程
- **不改狀態機、不碰 billing、不改爬蟲**：僅 `tasks.py` 的 deep_security_findings 呼叫兩個新函式
- **不寫 DB**：sri_scanner / dns_scanner 只回 `list[dict]`，由 tasks.py 統一 `Finding.objects.create()`
- **既有掃描不受影響**：新 scanner 只在 deep scan 路徑下執行（與現有 ssl/cookie/header scanner 同層）
- **新相依 dnspython**：已加入 pyproject.toml，Docker 重建後自動安裝

## 驗證方式

- **單元測試**：`sri_scanner` 8 項 + `dns_scanner` 14 項 + `owasp_mapper` 1 項（新 rule_id 對映）
- **`uv run python backend/manage.py test apps.scans`**：全套件 195+ 項全綠
- **`uv run ruff check backend`**：lint 無誤
- **Docker E2E**：待 Task 7 人工從 UI 觸發掃描觀察 findings（新 scanner findings 應出現在報告 security 分類）

## severity 校準說明

| 問題 | severity | 理由 |
|---|---|---|
| SPF 缺失 | MEDIUM | 可被利用假冒網域寄信，影響中等，但需搭配其他條件 |
| SPF `+all` | HIGH | 明確允許任意主機以該網域發信，直接高風險 |
| DMARC 缺失 / `p=none` | LOW | 缺少政策但不立即可利用；`p=none` 等於無保護但無動作 |
| DNSSEC 缺失 | LOW | 業界最佳實務建議，缺失不代表立即被利用 |
| SRI 缺失（外部 CDN）| LOW | 供應鏈風險，需 CDN 被攻破才能觸發；去重後避免噪音 |
