# 資安發現類型標示（roadmap §5 第 1 項、§12 第 6 項第一階段：只標示）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- 新增 `security/finding_kind.py`：依 rule_id、標題、證據來源，把資安發現分成四類：
  - **設定建議**：安全標頭、Cookie、DNS、TLS、SRI、ZAP 被動告警、security.txt。
  - **曝露面**：版本號、技術標頭、管理入口、公開聯絡資料、低風險探測檔案。
  - **疑似弱點**：依版本比對的 CVE、秘鑰樣式、Nuclei 樣板命中、AI 觀察、可能缺 CSRF token、CORS 帶憑證。
  - **已驗證弱點**：sqlmap 確認注入、實際下載到的高風險檔案（.env、.git 等，高／重大）。
  - 掃描本身的說明（例如 WAF 之後 0 項發現）不分類。
- 不看 `Finding.confidence`：既有資料幾乎都是預設 1.0，代表「沒有校準」，不是「已確認」。
- 不影響分數與排序。類型在顯示時推得（`Finding.security_kind`／`security_kind_label` property），不寫 DB、不需 migration，舊掃描也有。
- 呈現：
  - API：`FindingSerializer` 兩個欄位、`projects.issue_groups`（問題分析）。
  - 前端：問題分析表的分類欄加類型徽章（文字、無左邊條）；掃描詳情判定證據加「資安類型」一格。
  - PDF 報告：每項追蹤列加「類型」，`RENDERER_VERSION` 16。
- 已重新產生 OpenAPI／前端型別。
- 文件同步：
  - security／scans／frontend CLAUDE.md。
  - roadmap §5 第 1 項、§12 第 6 項。
  - 需求書 ARGUS-F-013 說明與驗收項目。

## 真實資料核對
- 示範專案資料集（三次真實掃描）裡的每一筆資安 finding 都有歸類。
  - 設定建議：CSP、HSTS、HTTPS、XFO、nosniff、Cookie、SPF／DMARC、SRI。
  - 曝露面：X-Powered-By、個資兩種。
  - 疑似弱點：CSRF、jQuery 與 Apache／PHP 的 CVE。
  - 已驗證弱點：`.env` 外洩。
- 沒有類型的只有資料集裡沒有 rule_id 的摘要資料，不是 finding。

## 驗證方式
- 新增 `tests_security_finding_kind.py`（6 項）：
  - 四種類型的對映。
  - 掃描說明與非資安維度不分類。
  - serializer 欄位。
  - 問題分析分組。
  - 報告追蹤列。
- 前端 `ProjectPages.test.tsx`：資安問題分類欄顯示類型，其他維度不顯示。
- 全套後端測試、`ruff check backend`、`makemigrations --check`（無變更）。
- 前端 lint（0 error，1 個既有 warning）、typecheck、vitest 240 項。

## 尚未做
- 規則產生 confidence 的方式。
- 低可信度影響排序或扣分（§12 第 6 項後續）。
