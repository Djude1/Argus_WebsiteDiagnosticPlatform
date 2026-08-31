# 分數權重比例修正 + 報告輸出 AI 提示詞

**日期**：2026-08-31
**操作者**：Claude
**背景**：使用者要求我自行評估兩項待決事項（`SCORE_DECAY_CONSTANT` 是否調整、`ai_explanation` 等死欄位如何處置）並執行。

## 變更內容

### 1. `backend/apps/scans/scanners.py` — 嚴重度權重比例
- `severity_penalty` 由 `35/25/14/6/0` 改為 `60/35/12/4/0`（critical/high/medium/low/info）。
- `SCORE_DECAY_CONSTANT` **維持 50.0 不變**。
- 對照表註釋同步更新。

### 2. `backend/apps/scans/tests_scoring_and_report_grouping.py`
- 新增 `test_severity_outweighs_volume`：鎖住「1 個 critical 必須比 6 個 low 扣更兇」。
- `test_many_problems_do_not_collapse_to_zero` 改寫為 `test_score_keeps_resolution_in_the_realistic_range`：原本用 10 vs 30 個高風險，那是我隨手挑的數字、不對應任何真實網站；改成 3 vs 8 個中風險（真實網站落點）並加上「不得低於 30」的下界斷言。

### 3. `backend/apps/scans/reports.py` — 每筆 finding 輸出 AI 提示詞
- 新增「AI 提示詞（可直接複製貼給 AI 助手取得進一步說明）」段落，輸出 `Finding.ai_handoff_prompt`。
- **必須套 `mask_pii_evidence()`**：`build_ai_handoff_prompt()` 內嵌原始 `evidence`，不遮罩等於從後門把個資漏回這份會被轉寄的報告。已用測試鎖定。
- 上限 1500 字，超過截斷。

### 4. `backend/apps/scans/tests_report_content.py`
- `test_finding_carries_a_pasteable_ai_prompt`、`test_ai_prompt_is_pii_masked_like_evidence`。

### 5. 文件同步
- `backend/apps/scans/CLAUDE.md`：記載報告改輸出 `ai_handoff_prompt` 與必須遮罩的理由。

## 原因

### 為什麼調的是權重比例而不是衰減常數

先把 4 個候選常數（40/50/60/70）對 6 種真實網站輪廓跑數字，發現**調常數解決不了問題**——真正的缺陷是嚴重度比例太平：

| | 現行 35/25/14/6 | 調整後 60/35/12/4 |
|---|---:|---:|
| 1 個 critical | 50 | **30** |
| 6 個 low | 49 | **62** |

現行權重等於宣告「六個缺 canonical URL ≈ 一個嚴重漏洞」，站不住腳。而這是比例問題，單一常數（數學上等同對所有 penalty 等比縮放）動不了它。

調整後各輪廓分數：

| 網站輪廓 | 現行 | 調整後 |
|---|---:|---:|
| 幾乎沒問題（1 低） | 89 | 92 |
| 體質不錯（2 低 1 中） | 59 | 67 |
| 典型中小企業（缺 CSP/HSTS/DMARC/DNSSEC + 2 SEO） | 35 | **45** |
| lqll 這種（含 1 個 PII 高風險） | 14 | 15 |
| 疏於維護（+3 高風險） | 3 | 2 |

原本「典型中小企業」只拿 35 分過於嚴苛——那些是體質項目不是「網站壞了 65%」。

### 為什麼死欄位既不實作也不移除

`ai_explanation` / `ai_remediation` / `llm_model` / `llm_generated_at` 維持現狀（保留欄位、無寫入點、報告不聲稱），改為輸出既有的 `ai_handoff_prompt`：

- **每筆 finding 都已經有值**，`build_ai_handoff_prompt()` 產生的內容包含類型／嚴重度／描述／證據／修補方向與指示語，直接可用。
- 實作 LLM 解釋是獨立功能專案：每次掃描 20-40 筆 finding，逐筆呼叫 LLM 會改變 coin 的單位成本結構，且與「Evidence-first、AI 不直接判斷網站好壞」的產品原則相衝突。
- 移除欄位要 migration，且失去日後實作的彈性，換來的只是少 4 個空欄位。
- 輸出提示詞用約 10 行程式碼交付了使用者真正想要的東西（拿到深入說明），成本為零。

## 影響範圍

- **所有分類分數再次改變**。既有掃描的 `category_scores` 已寫入 DB，不會回填重算；要看到新分數必須跑新掃描。
- 報告每筆 finding 多一段 AI 提示詞（上限 1500 字），報告長度會增加。
- 未動：`SCORE_DECAY_CONSTANT`、去重邏輯、排序、授權／範圍／警示章節、`security/` 子套件、前端。

## 驗證方式

- `uv run ruff check backend` → All checks passed
- `uv run python backend/manage.py test apps` → **Ran 712 tests，OK（skipped=1）**（前次 709，+3 新測試，無回歸）
- 實際產出報告目視確認：AI 提示詞內的手機號碼顯示為 `09******78`（遮罩生效，非原始號碼）；1 高 + 1 中的 SECURITY 得 39 分。

## 本次同時完成的部署追蹤（前一次 push 的後續）

commit `5672144` 的部署鏈已全部走完並實測確認：

- Quality Gate ✅ / Build & Push Backend Image ✅（皆為 SHA `5672144`）
- bot 回寫 `cc71fd7` → `k8s/kustomization.yaml` 的 `argus-backend` 改為 `sha-5672144`
- **正式站已生效**：以「登入失敗狀態碼」當部署探針，`POST /api/auth/email-login/` 帶錯誤帳密由 **400 翻成 401**，證明新 image 已服務（健康檢查 200 無法證明版本）。兩個網域 `/api/health/ready/` 皆 200，migration `0010` 未阻斷服務。

## 未處理／待決事項

- **分數曲線在低分區仍然壓縮**（疏於維護 2 分、災難級 0 分）。這是指數衰減的固有性質；到那個程度的網站對使用者而言訊息相同（「全面處理」），視為可接受的取捨，未加人工地板。
- **體質項目的數量仍可能蓋過單一高風險 finding**（lqll 輪廓：1 個 high 佔 35 分，其餘體質項目合計 60 分）。要徹底解決需改成「最嚴重項目定上限、數量在帶內移動」的分級模型，屬產品層決策，未做。
- 既有掃描分數不回填重算（如上）。
- 第三階段（C 可讀性與術語 + D 排版格式）尚未開始。
- **compose DB 仍是空的**，至今沒有跑過一次真實掃描的端到端報告。
