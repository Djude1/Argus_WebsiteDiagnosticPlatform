# Phase 1：PII 外洩偵測（個資掃描）

**日期**：2026-05-27
**操作者**：Claude
**Phase**：1 / 4（後續還有 JS secret、錯誤訊息、敏感路徑探測）

## 變更內容

- `backend/apps/scans/scanners.py`
  - 新增常數：`EMAIL_PATTERN` / `TW_MOBILE_PATTERN` / `TW_NATIONAL_ID_PATTERN` / `CREDIT_CARD_PATTERN` / `_TW_ID_LETTER_VALUES`
  - 新增驗證函式：`is_valid_tw_national_id()`（內政部演算法檢查碼）、`is_valid_luhn()`（信用卡 Luhn 演算法）
  - 新增 `detect_pii_in_text()`：統一入口，回傳分類後去重的 PII 結果
  - 新增 `analyze_data_exposure()`：產生 SECURITY HIGH finding，evidence 顯示原始 PII
  - `analyze_page()` pipeline 加入 `analyze_data_exposure()`，admin 路徑也會跑（後台外洩個資更嚴重）
- `backend/apps/scans/tests.py`
  - import 加入 4 個新函式
  - 新增 `PiiDetectionTests` class，20 個測試覆蓋：身分證檢查碼、Luhn、各 pattern 偵測、誤判緩解、警示文字、finding 結構、analyze_page 整合

## 原因

教授希望 ARGUS 能偵測學校網站的資安弱點，特別是「學生個資裸奔」這類問題。使用者明確要求：
- 不做遮罩，evidence 顯示原始個資（為了給教授看實際洩漏內容）
- 違法風險由使用者自行承擔
- 先用自己的靶機網站測試

本次實作為 Phase 1，僅做被動偵測（regex 比對已抓回的 HTML），不主動探測對方系統。

## 設計取捨

### 為什麼用檢查碼驗證

- 身分證號 regex `[A-Z][12]\d{8}` 對「ABC123456789」這種亂寫會誤判，加內政部檢查碼演算法後僅合法號碼才入列
- 信用卡 regex 對 13-19 位數字幾乎所有商品編號都會誤判，加 Luhn 後僅符合卡號數學特性的才入列
- 這兩類加檢查碼後 false positive 大幅降低（測試覆蓋此情境）

### 為什麼 evidence 顯示原始 PII（不遮罩）

使用者明確要求兩次，理由：要展示給教授看實際外洩內容，遮罩會喪失警示效果。法律風險由使用者承擔。

**最小警示機制（Claude 強制加上）**：
- Finding description 開頭固定加 `⚠️ 此項目顯示原始個資，請依個資法妥善處理本報告`
- 後續 Phase 4 會在前端報告下載前加確認彈窗

### 為什麼歸 SECURITY HIGH

- Category：與「頁面未使用 HTTPS」「缺少 CSRF token」等同屬資安問題，歸 SECURITY 一致
- Severity：HIGH（個資外洩在個資法下罰責嚴重，但不到 CRITICAL）
- priority_score 85：排在 HTTPS 缺失（90）之後、CSRF（64）之前

### 為什麼每類最多列 50 筆

avoid evidence 欄位被個資灌爆（make_finding 還會截到 4000 字）。極端情境（例如某頁有 10000 筆 email）使用者仍能從「N 筆」總數判斷嚴重性。

### 為什麼從 raw HTML 偵測而非 visible text

raw HTML 是 visible text 的超集——`data-` 屬性、hidden input、`<script>` 內 JSON 字串裡的 PII 都會被找到，這些往往是更危險的洩漏（使用者看不到但 crawler/attacker 能讀）。

## 影響範圍

- 既有 SEO/AEO/GEO/Security finding 不受影響
- admin 路徑（`/admin` 等）原本只跑 SECURITY，現在多跑一次 PII 偵測——後台洩漏個資是嚴重問題，必須檢查
- binary 資源（.pdf、.apk 等）仍只跑 SECURITY，不跑 PII（沒有 HTML 內容可偵測）
- CF challenge 頁面（已在前一次任務加偵測）會被 `tasks.py:108-109` 攔下，PII 偵測不會在攔截頁上跑（避免對 CF 自己生成的內容做偵測）

## 驗證方式

```powershell
uv run python backend/manage.py test apps.scans.tests.PiiDetectionTests -v 2
```

結果：**20 tests passed**，耗時 0.012s。

```powershell
uv run python backend/manage.py test apps.scans
```

結果：120 tests，119 pass、1 fail。唯一 fail 是 pre-existing 的 `test_analyze_page_returns_seo_geo_and_security_findings`（斷言「缺少 JSON-LD 結構化資料」但 scanners.py 已改為「可補充 JSON-LD 結構化資料」），與本次修改無關。

## 後續 Phase（給未來自己看）

- **Phase 2**：JS/HTML 內 secret 偵測（AWS key / JWT / API key / DB 連線字串），架構與 PII 類似（regex pattern）
- **Phase 3**：錯誤訊息外洩偵測（SQL error / stack trace / PHP warning），仍是被動 regex
- **Phase 4**：敏感路徑探測（`.env` `.git` 等 ~20 個 well-known paths），歸 `active_probes.py`，需 `active_testing_authorized=True`；同時在前端加報告下載前的「含未遮罩個資」確認彈窗，並新增 `MD/penetration_targets.md` 列合法靶機（DVWA / Juice Shop / HackTheBox）
