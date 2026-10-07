# 商業模式與定價健檢、正式商業模式計劃書

**日期**：2026-10-07
**操作者**：Claude

## 變更內容
- 新增 `docs/business-model-plan.md`：Argus 正式商業模式計劃書兼定價健檢報告。
  - 現況盤點：點數制度、購點與訂閱方案、各掃描類型預扣與結算金額（附程式出處）。
  - 評估一：新用戶 200 點無法啟動五維整站掃描（預扣 520 點）；輕量訂閱（300＋免費 200）同樣無法啟動。
  - 評估二：逐頁分析與 AEO 問答檢測不呼叫模型（0 token）；token 只花在 Hermes-Agent、頁面優化、修正產出；深度資安 Agent 未單獨收費且派工無硬上限，是唯一成本缺口。
  - 評估三：與 Semrush／Sitechecker／Detectify 月費比較，Argus 約為 1/3–1/4，但每月可做完整掃描次數偏少。
  - 建議方案：新手禮 600 點、餘額不足自動降頁數、訂閱以「每月完整掃描次數」重新配點（600／1,800／4,000）、深度資安附加費 50 點＋派工上限 6、頁面優化上限 50 點、贈點累積上限 600。
  - BMC 九宮格更新、財務預估（損益平衡、三情境）、KPI、成長路線、風險、待決策事項、外部價格來源。
- 所有數字標示【事實】或【假設】。

## 原因
使用者認為新註冊用戶預給點數不正常、至少應能完成一次完整掃描，並要求評估商業模式與定價是否合理、是否依 AI token 消耗，以及產出正式商業模式計劃書。

## 影響範圍
- 本次只新增文件，未改動任何計費參數或程式。
- 計劃書第十一章列出待決策事項；決定後的程式改動範圍（settings、billing/signals、訂閱方案 migration、掃描表單與 serializer、agent 派工上限）與競賽文件同步範圍已列明。
- 已知文件漂移（未在本次修正）：`專題文件生成/設計文件_圖表與成本模組.md` 5.4 節與 BMC 仍寫訂閱為「規劃中／無週期扣款」，實際已改為綠界定期定額（需求書已同步）。

## 驗證方式
- 計價、贈點、預扣與結算邏輯對照實際程式：`settings.py`、`billing/services.py`（`estimate_scan_cost`、`hold_for_scan`、`settle_scan_actual`）、`billing/signals.py`、`billing/migrations/0002、0009`、`scans/scan_plan.py`、`scans/tasks.py`（`stage_agent`）、`agent/runner.py`（8 種專家角色、無派工上限）、`agent/loop.py`（每 session token 上限）、前端 `MAX_SITE_SCAN_PAGES=50`。
- 確認 `scanners.py`、`aeo/`、`reports.py`、`katana_scanner.py` 未呼叫模型。
- 外部價格以網路搜尋取得（MiniMax-M3、Semrush、Sitechecker、Detectify），來源列於附錄，並註明需到官網再確認。
