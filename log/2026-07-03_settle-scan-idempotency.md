# settle_scan_actual 冪等修復

## 變更內容

**修改檔案：** `backend/apps/billing/services.py`

`settle_scan_actual` 新增前置冪等檢查與 0 元標記交易：

1. 函式開頭先查是否已有此 `scan_job` 的 `SCAN_REFUND` 交易，若有則整段跳過（含 `total_scans_used`）
2. 當 `refund_amount == 0`（實際頁數 == max_pages）時，建立 amount=0 的 `SCAN_REFUND` 標記交易，供未來冪等偵測

## 原因

原實作有兩個 bug：

**Bug 1：`total_scans_used` 重複累加**
```python
# 原本
wallet.total_scans_used += 1   ← 副作用先做
if refund_amount <= 0:
    return None                 ← 冪等 return 在後
```
重複呼叫 `settle_scan_actual` 時，第二次雖然 `refund_amount == 0`（沒錢可退），但 `total_scans_used` 仍會被 +1，導致「掃描次數」統計被灌水。

**Bug 2：無退款差額情境無冪等信號**
若 `actual_pages == max_pages`，原本不建立任何 `CoinTransaction`，導致下次呼叫時「已存在 SCAN_REFUND」的檢查失效。

## 行為說明

| 情境 | 首次呼叫 | 第二次呼叫（冪等測試） |
|---|---|---|
| 有退款差額（actual < max_pages） | 退差額、建立 SCAN_REFUND、`total_scans_used +1` | **整段跳過**，回傳 None |
| 無退款差額（actual == max_pages） | 建立 amount=0 SCAN_REFUND 標記、`total_scans_used +1` | **整段跳過**，回傳 None |
| 先呼叫 refund_full_for_scan 再呼叫 settle | — | **整段跳過**（refund_full 已建 SCAN_REFUND） |

## 影響範圍

- `wallet.total_scans_used` 統計正確性：重複呼叫不會再灌水
- `CoinTransaction` 稽核軌跡：多了一種 amount=0 的 SCAN_REFUND 標記交易（僅在 actual == max_pages 情境出現）
- 公開簽章不變：`(user, scan_job, actual_pages) -> CoinTransaction | None`
- 呼叫者不需修改

## 驗證方式

- AST 語法檢查：`python -c "import ast; ast.parse(...)"` — 通過
- 全套 billing 測試（35 項）— 全部通過
- 語意驗證：在冪等前置檢查前 `select_for_update`，確保跨 process 呼叫也序列化
