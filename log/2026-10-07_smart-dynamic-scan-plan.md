# 智慧動態掃描（Smart Dynamic Scan）實作計劃文件

**日期**：2026-10-07
**操作者**：Claude

## 變更內容
- 新增 `docs/adr/0004-smart-dynamic-scan.md`：Argus 第三種掃描模式「智慧動態掃描」的完整實作計劃（ADR 形式）。
  - 流程：指紋辨識 → 風險面發現 → 動態模組選擇 → 深度掃描。
  - 兩條定錨原則：只加不減（Additive-only）、預扣上限+實跑結算。
  - 資料模型：`ScanJob.scan_mode` 增 `smart`、新增 `fingerprint` 與 `dynamic_modules` 兩個 JSONField。
  - 核心新零件 `SiteFingerprint`（決策導向指紋收斂層，與展示用技術棧分開）與 `stage_fingerprint`。
  - 兩段式計畫：既有 `build_scan_execution_plan` 不動（基礎全掃底線）＋ `augment_plan_with_fingerprint`（只開不關）。
  - 新深度模組：Auth/Session/Cookie、API 安全、WordPress 專屬、Drupal/Joomla。
  - 計費改上限預扣+結算退差額（複用 rebuild 的 hold/settle 模式）。
  - 三階段落地（階段 1 指紋只記錄不改行為 → 階段 2 動態加掃+計費 → 階段 3 旗艦模式+前端呈現），每階段可獨立上線與驗證。
  - 可接外部工具對照（Nuclei API 模板、WPScan 思路、OSV.dev/EPSS）、風險與緩解、替代方案。

## 原因
使用者參考商用掃描器（Acunetix Advanced Dynamic Scan）的「先認識網站再決定怎麼掃」思路，希望 Argus 做出與一般固定 checklist 掃描器的差異化。評估後確認此方向吃到 Argus 現有架構的甜蜜點（指紋零件已存在於 `tech_stack.py`／`katana_scanner`／`infra_scanner`，掃描階段已模組化成 `stage_*`），缺的是「指紋→模組選擇」決策層與配套計費模型，遂先產出完整實作計劃文件供後續分階段實作。

## 影響範圍
- 本次只新增文件，**未改動任何掃描程式或行為**。
- 後續實作需遵守：Migration 鐵律（欄位一律新增）、`scans/CLAUDE.md` 的 scanner 回傳契約與狀態機規則、preflight 掃描驗證閘門。

## 驗證方式
- 對照 2026-10-07 實際程式撰寫：已讀 `scan_plan.py`（確認 `ScanExecutionPlan` 現有欄位與 `build_scan_execution_plan` 只依 `ScanJob` 欄位）、`tech_stack.py`（確認指紋訊號現況與「只供報告」）、`tasks.py` 的 `stage_*` 階段清單與 `stage_site_profile` 位置。
- 文件為計劃層級，無程式可跑測試；落地時每階段再依文件第 7 節的驗證步驟執行。
