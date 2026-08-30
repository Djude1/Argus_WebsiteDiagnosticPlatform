# 掃描報告品質改善 第一階段：分數計算與 finding 排序

**日期**：2026-08-30
**操作者**：Claude
**依據**：[`docs/scan-report-quality-audit-2026-08-30.md`](../docs/scan-report-quality-audit-2026-08-30.md) 的第一階段（A1、A3、A4、A5、B1、B2、B4，另含 B5）

## 變更內容

### 1. `backend/apps/scans/scanners.py` — `make_finding()` 補 priority_score 預設
- 新增 `_SEVERITY_DEFAULT_PRIORITY`（critical 90 / high 75 / medium 50 / low 25 / info 10）。
- 呼叫端沒傳 `priority_score` 時依 severity 給預設，不再留 `None`。呼叫端傳明確值則不覆寫。
- **`security/` 的 7 個 scanner 全部透過 `make_finding()` 產生 finding，所以改一處即全數涵蓋**，不需逐檔修改。

### 2. `backend/apps/scans/models.py` — `Finding.Meta.ordering`
- `priority_score` 改用 `F("priority_score").desc(nulls_last=True)`。
- `severity` 改用 `Case/When` 的風險序（critical → info），取代 CharField 的字母序。
- migration `0010_alter_finding_options.py`（`AlterModelOptions`，DB 層無操作）。

### 3. `backend/apps/scans/scanners.py` — `calculate_scores()` 重寫
- 新增 `_dedupe_findings_for_scoring()`：同一分類內同一 `rule_id`（缺漏時退回 title）只計一次。
- `info` penalty 由 2 改為 0。
- 分數公式由 `max(0, 100 - penalty)` 改為 `round(100 * exp(-penalty / SCORE_DECAY_CONSTANT))`，常數 50.0。
- 未評估的分類不再寫進 `category_scores`（缺鍵＝未評估），`overall_score` 的分母與 `category_scores` 的鍵集合一致。
- `top_actions` 改由去重後的清單取前 5。

### 4. `backend/apps/scans/reports.py` — 分組與摘要
- `_group_findings_for_report()` 合併鍵由 `(rule_id, evidence)` 改為 `rule_id`；`rule_id` 為空時退回 `finding.pk`；`pages` 清單去重。
- 摘要改為逐一列出全部 5 個分類，缺鍵顯示「未評估（本次掃描未執行此項檢查）」，並加一段說明整體分數的算法。

### 5. 新增 `backend/apps/scans/tests_scoring_and_report_grouping.py`（15 項測試）
涵蓋跨頁去重、info 不扣分、未評估分類缺鍵、整體分數與列出分類一致、分數不塌陷、top_actions 去重、priority_score 預設與嚴重度序、ordering 的 nulls_last 與風險序、報告分組。

### 6. 文件同步
- `backend/apps/scans/CLAUDE.md`：新增「分數計算契約」章節，記載四條規則、ordering 的兩個 DB 差異陷阱，以及 **`category_scores` 不保證含全部 5 個分類、取值一律用 `.get()`**。
- `backend/apps/scans/tasks.py`：`tested_categories` 上方的註釋原本描述「ux 只是恰好維持在 100」，已同步為新行為。

## 原因

`argus-scan-25-report.docx` 出現「整體 39、SECURITY 0、UX 100」的不合理分數與「低風險排在高風險前面」的報告順序，稽核後定位到四個獨立成因：

1. **顯示合併、計分不合併**：報告用 `_group_findings_for_report()` 把重複問題併成一筆，`calculate_scores()` 吃的卻是合併前的原始陣列。PII 出現在 3 個頁面被扣 25×3=75 分，佔掉 SECURITY 總懲罰 153 分的一半。
2. **`info` 倒扣**：報告最後一項「偵測到 Cloudflare WAF 保護，屬正向安全指標」是 `severity=info`，舊表扣 2 分——好消息倒扣。
3. **未測仍給滿分**：`ARGUS_AGENT_ENABLED` 預設 False，UX 完全沒測，但 `category_scores` 照樣回傳 100 印在報告上；同時 UX 被排除在 overall 平均外卻沒說明，使用者拿 5 個數字算不出 39。
4. **PostgreSQL 與 SQLite 的 NULL 排序相反**：`security/` 全部 7 個 scanner 都不給 `priority_score`，`ordering = ["-priority_score", ...]` 在 PostgreSQL 是 NULLS FIRST、SQLite 是 NULLS LAST。**本機用 SQLite 開發永遠複現不出來，只有正式站的使用者會看到低風險項目被頂到最前面**；同一成因也讓這些 finding 因 `priority_score or 0` 永遠進不了「優先改善建議」。

另外 `severity` 是 CharField，字母序是 `critical < high < info < low < medium`，`info` 會插到 `low` 與 `medium` 前面。這與 `priority_score` 改的是 `Meta.ordering` 同一行，一併修正。

## 影響範圍

- **`category_scores` 的鍵集合改變**（破壞性）：不再保證含全部 5 個分類。已逐一確認全部消費端：
  - `views.py:410` dashboard 聚合已有 `isinstance(score, (int, float))` 與 `if data["count"]` 防護，缺鍵安全；行為反而更正確（舊版每筆掃描都貢獻 ux=100，把 UX 平均灌成無意義的 100）。
  - `frontend/src/features/admin/AdminPages.jsx:1294` 用 `Object.entries()` 迭代，缺鍵只是少顯示一項，不會出現 `Math.round(null)=0` 或 `NaN`。
  - `reports.py` 已改為逐一列出 5 個分類並顯示「未評估」。
  - serializer / admin 皆為透傳，無假設。
  - 前端另兩處 `categories` 用法（`PublicPages.jsx:802` 快速掃描、`AuthenticatedPages.jsx:349` findings 計數）走不同 API，不受影響。
- **既有掃描資料不受影響**：舊 `ScanJob.category_scores` 已含 5 個鍵，報告照舊顯示分數，不會變成「未評估」。分數不會回填重算。
- **未動的部分**：`security/` 7 個 scanner 一行未改；PII 遮罩規則（`security/redaction.py`）未動；狀態機與 billing 未動。

## 驗證方式

- `uv run ruff check backend` → All checks passed
- `uv run python backend/manage.py check` → no issues
- `uv run python backend/manage.py test apps` → **Ran 699 tests，OK（skipped=1）**（改動前 684，+15 新測試，無回歸）
- **PostgreSQL 實跑**（本機 SQLite 蓋不到 B1，這是必要步驟）：把改動 `docker compose cp` 進 compose 的 `web` 容器，`manage.py test apps.scans.tests_scoring_and_report_grouping` → 15 項全過。
- **測試有效性反證**：把 `models.py` 還原成 HEAD 版本再於 PostgreSQL 重跑 `FindingOrderingTests` → 2 項全失敗，`test_severity_tiebreak_follows_risk_not_alphabet` 實際得到 `['critical', 'info', 'medium']`，確認測試鎖得住而非空殼。
- **依 scan 25 報告逐項重算對照**（腳本重建 finding 清單）：

  | 分類 | 舊 | 新 |
  |---|---|---|
  | SEO | 32 | 70 |
  | AEO | 100 | 100 |
  | GEO | 24 | 59 |
  | SECURITY | 0 | 14 |
  | UX | 100 | 未評估 |
  | **整體** | **39** | **61** |

  已評估的 4 個分類平均 = 61 = 整體分數（舊版列 5 個卻只平均 4 個，對不出 39）。`top_actions` 由「PII×3 + JS渲染×2」變成 5 個不同問題，且高風險 PII 排第一。

## 未處理／待決事項

- **`SCORE_DECAY_CONSTANT = 50.0` 是產品參數，需要你確認**。目前值讓「1 個中風險 → 76 分、1 個嚴重 → 50 分、累積 100 分懲罰 → 14 分」。調小更嚴格、調大更寬鬆，改一個常數即可。
- **`top_actions` 只依 `priority_score` 排序**。scan 25 重算後 5 個名額全是 SECURITY（該站確實資安最差），但這代表其他分類可能長期擠不進優先建議。是否要保證分類多樣性是產品決策，未動。
- **admin 後台不顯示「未評估」**：`AdminPages.jsx` 缺鍵時直接不顯示該分類。不誤導（比顯示假的 100 好），但沒有明確標示，屬前端範圍，未動。
- **`confidence` 未納入計分**（稽核補充的 N2）。目前 `confidence` 幾乎都是 1.0，納入等於無操作，未做。
- 第二階段（F1 附錄不實陳述、E5 授權聲明、F2 掃描範圍、F3 warning_summary）尚未開始。
- **compose DB 仍是空的**（ScanJob=0），本次全部驗證來自單元測試與腳本重算，**沒有端到端跑過一次真實掃描產出新報告**。
