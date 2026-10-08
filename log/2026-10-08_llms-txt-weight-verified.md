# 驗證 llms.txt 不扣分（roadmap §2 AEO 第 7 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- 核對 roadmap 標「待驗證」的項目：llms.txt 是否已降級、不與成熟 SEO 規則等價扣分。
- **核對結果：已經是**。
  - `scanners.analyze_site_signals` 的「網站未提供 llms.txt」嚴重度是 `info`。
  - 計分權重 0（`SEVERITY_PENALTY`），也不進優先改善建議。
  - 描述寫明「新興做法、尚未成為正式標準」。
  - 報告依據 `RULE_BASIS["GEO_LLMS_TXT_C8A1E5700E"]` 寫明缺少不會讓網站無法被引用。
  - 沒有檢查 `llms-full.txt`。
- 原本只有措辭有測試；新增 `tests_accuracy_review.test_llms_txt_does_not_deduct_score`，鎖定嚴重度為 info，且 GEO 分數維持 100、權重 0。
- roadmap §2 第 7 項改為「已驗證」。

## 原因
roadmap 該項標「待驗證」；不鎖定的話，之後有人把嚴重度改回 low 就會開始扣分。

## 影響範圍
只新增測試與文件，程式行為不變。

## 驗證方式
- `tests_accuracy_review`：8 項 OK。
- `ruff check backend` 通過。
