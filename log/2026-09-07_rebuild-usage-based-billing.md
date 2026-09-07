# 網頁複刻改為按實際用量結算

**日期**：2026-09-07
**操作者**：Claude

## 變更內容

把複刻的固定價改成「預扣額度 → 依實際用量結算 → 退差額」，與掃描既有的
`hold_for_scan` / `settle_scan_actual` 同一套模式。

- `billing/services.py`：`estimate_rebuild_cost` → `estimate_rebuild_hold`；
  新增 `rebuild_coins_for_usd`（無條件進位 + 最低消費）與 `settle_rebuild_actual`（冪等）
- `SiteRebuild.coins_charged`：結算後實收點數，從 `CoinTransaction` 回推
- `GET /rebuilds/cost/` 回傳欄位 `cost` → **`hold`**：叫 cost 會讓前端把額度當價格顯示
- 前端文案改為「先預扣 N 點，完成後依實際用量結算、退回差額」，完成後顯示實收
- 設定拆成三個：`ARGUS_COIN_REBUILD_HOLD`(30) / `ARGUS_COIN_PER_USD`(100) /
  `ARGUS_COIN_REBUILD_MIN`(1)

## 原因

使用者問「不能像主流 API 那樣按用量即時扣嗎」。可以，而且**這個 repo 本來就
有這個模式**——掃描就是預扣 `max_pages` 再依實際頁數退差額。我當初給複刻用
固定價，是在同一個計費系統裡引入了第二套規則，不一致。

資料也早就有：opencode 每次回應都帶實際花費，`SiteRebuild.cost_usd` 已經在存了。

## 設計決定

**實際用量超過預扣時只收預扣額，不追扣。** 追扣等於在使用者沒同意、也沒再
檢查餘額的情況下二次扣款，可能把餘額扣成負數。

**換算率的推導**（不是憑感覺）：購點四方案平均 1 coin ≈ NT$0.845，USD/NTD 取
32，純成本約 38 coin/USD。預設 `ARGUS_COIN_PER_USD=100` 約為純成本 2.6 倍。

## 影響範圍

- 新增 migration `rebuild/0002`
- **目前最低消費才是決定價格的那一項**：實測 $0.001333 × 100 = 0.13 點，
  遠低於下限 1 點——現階段等於固定收 1 點。要讓用量真的浮動，得等成本上到
  0.01 USD 以上，或調高 `ARGUS_COIN_PER_USD`
- `/rebuilds/cost/` 的回應欄位改名，前端已同步

## 驗證方式

- `apps.rebuild` + `apps.billing` 84 tests OK；root `tests/` 42 OK
- 前端 `vite build` 通過
- **對真實 agent 驗過**：$0.001333 → 預扣 30、實收 1、退回 29，餘額 500→499
  ```
  rebuild_hold    -30  餘額=470  網頁複刻預扣上限（page=1）
  rebuild_refund  +29  餘額=499  實際用量 1 coin，退回未使用的 29 coin
  ```
- 測試涵蓋：正常結算退差額、用量超過預扣時封頂不追扣、免費模型收最低消費、
  結算冪等
