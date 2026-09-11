# 票03：billing 產生額度與 Kind 擴充

**日期**：2026-09-11  
**操作者**：Claude（ZCode）

## 變更內容
- `backend/apps/billing/models.py`：`CoinTransaction.Kind` 新增 `fixgen_grant`／`fixgen_charge`／`fixgen_refund`（migration `0007_alter_cointransaction_kind`）。
- `backend/apps/billing/services.py` 新增（全走 select_for_update＋atomic 既有模式）：
  - `grant_fixgen_entitlement`：付費掃描（淨扣 > 0）結算後附贈 1 次額度，同掃描只贈一次（冪等）。
  - `fixgen_entitlement_available`：額度可用判定＝有贈與且 0 元扣款未被 0 元退款抵銷（失敗重試後額度回得來）。
  - `charge_fixgen_generation`：觸發前計費——額度內 0 元消耗、額度外扣 `ARGUS_COIN_FIXGEN_GENERATION`（預設 30，暫定值）固定點數；不足 raise `InsufficientCoinError`。
  - `refund_fixgen_generation`：失敗退費——點數退點（正數）、額度返還（amount=0）；冪等。
  - `is_paid_tier`：free/paid 自動判定（曾購點數包 `total_purchased_ntd>0` 或完成付費掃描 `total_scans_used>0`）。
- `backend/apps/scans/tasks.py`：掃描結算成功後呼叫 `grant_fixgen_entitlement`（獨立 try——贈與失敗只記 warn log，不影響掃描結果與結算狀態）。
- `backend/config/settings.py`：`ARGUS_COIN_FIXGEN_GENERATION`（30，上線前以 rebuild token 成本校準）。
- 文件同步：billing/CLAUDE.md services 表＋kind 表、backend/CLAUDE.md CoinTransaction 速查。

## 原因
spec `docs/specs/0002-fix-output.md` 票 03（`.scratch/fix-output/issues/03`）：付費掃描附贈 1 次產生額度、額度外固定 30 點、失敗全額退點；額度以交易紀錄表達（不新增模型、不動 wallet 欄位），帳目唯一事實來源維持 CoinTransaction。

## 影響範圍
- 掃描完成路徑多一個冪等贈與呼叫（隔離於結算 try 之外，失敗僅記 log）。
- 尚未與觸發 API 接線（票 04）；本票完成後額度會開始累積但無消耗入口。

## 驗證方式
- `uv run python backend/manage.py test apps.billing.tests_fixgen` → 8 tests OK（TDD：先 red 後 green；測試以 `_balance()` 重讀 DB 避開 user 建立時月贈點 signal 造成的快取失真）。
- `apps.billing apps.scans.tests_settlement` 55 tests OK（結算路徑接線無副作用）。
- 完整套件 921 tests：僅 1 個既有環境錯誤（report 檔案鎖定，前兩票已驗證與改動無關）；`ruff check` 通過。
