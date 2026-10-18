# 跨層去重 Pass 3：確定性規則 ↔ Agent 跨類別橋接（修密碼明文重複）

**日期**：2026-10-18
**操作者**：Claude
**來源**：使用者在最新報告（新 image）指出有兩筆一模一樣的發現——一個 AI Agent、一個前面階段的確定性規則。

## 問題
同一個問題（授權站 `/management/login` 密碼欄 `type="text"` 明文）被兩層各報一次：
- 確定性 `form-password-unmasked`（form_scanner，類型「設定建議」）
- Agent `agent-observed-security-<雜湊>`（類型「疑似弱點」）

現有跨層去重只有兩個 pass：(1) 確定性 exposure ↔ Agent 同端點；(2) Agent↔Agent 同資源＋同
`vuln_class`。這組跨不到：rule_id 不同、且 Agent 密碼標題的 `vuln_class` 落在 `other`（沒有密碼／
遮罩關鍵字），(resource, vuln_class) 配不起來。計分因此扣兩次、報告列兩次。

## 修法（cross_layer.py Pass 3）
- `_BRIDGE_CONCEPTS`：確定性 rule_id → 能認出等義 Agent 觀察的「關鍵字群」（每群任一命中、各群都要
  命中才算同一件事）。目前只列實際重疊的一組：`form-password-unmasked` ↔（密碼/password）且
  （`type="text"`／明碼／明文／遮蔽／遮罩／mask／plaintext）。
- `_resource_of`：資源路徑優先 endpoint／observed_endpoint，其次 `evidence_json.url`（form_scanner 把
  頁面網址存在 url，不是 endpoint）。form_scanner 與 Agent canonical 後都是 `/management/login`。
- Pass 3：先蒐集每個橋接概念在確定性層已覆蓋的資源，再把同一頁、關鍵字命中的 Agent 發現丟掉，
  **保留確定性那筆**（可重現、綁定頁面、措辭穩定）。被丟的連 DB 列一起刪（沿用 stage_scoring 機制）。

## 刻意保守（避免誤丟 Agent 獨有觀察）
- 必須有對應的確定性發現在同一頁，才會併；沒有就保留 Agent。
- 關鍵字要「每一群都命中」：同一頁但 Agent 講別的問題（如 XSS）不會被誤丟。
- 只列實際看到會重疊的組合，不做泛化比對。

## 驗證
- `tests_cross_layer.BridgeConceptMergeTests`（4）：同頁丟 Agent、不同頁都留、無確定性對應則留 Agent、
  同頁但無關 Agent 發現不誤丟。`apps.scans.tests_cross_layer`＋`tests_coverage` 共 48 項通過；ruff 乾淨。
- 文件同步 `security/CLAUDE.md`、`scans/CLAUDE.md`。

## 本輪報告審查（E43A，新 image）結論
資安深度已完全回來且更準：4.1 未授權 pastProjects（Agent）、4.2 api-docs 含內網 IP 這次由**確定性
探測** `exposure-file-apidoc` 抓到（類型已驗證弱點）、4.4/4.6 內網 IP 與 GET 傳密碼判定合理。CDN-skip
生效（略過 Nuclei 不再空等）、ZAP 從 502 變逾時（Host 修法通了、連得到 API）。唯一冗餘＝本次修掉的
密碼明文重複。Nuclei/Katana 在 Cloudflare 後 0 項為正常（CDN 過濾），非誤判。

## 備註
不含真實站名／路徑／機密值（ntubimdbirc 的 api-docs／內網 IP 仍未修補，報告請勿對外流通）。
