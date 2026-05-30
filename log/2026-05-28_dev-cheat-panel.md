# 測試用惡搞 Coin 面板

**日期**：2026-05-28  
**操作者**：Claude

## 變更內容

### 新增 / 修改
- `backend/apps/billing/views.py`：新增 `dev_cheat_coins` 端點
  - `POST /api/billing/dev-cheat/` — 僅在 `DEBUG=True` 時可用
  - `mode=set_max`：將餘額設為 INT32_MAX（2,147,483,647）
  - `mode=add_max`：在現有餘額上疊加 INT32_MAX
  - 底層呼叫 `billing/services.py` 的 `admin_adjust()`，符合唯一入口原則
- `backend/apps/billing/urls.py`：新增路由 `dev-cheat/`，附 TODO 註解提醒上線前移除
- `frontend/src/App.jsx`：`PurchasePage` 底部加入惡搞測試面板
  - 需登入才顯示（`accessToken` 判斷）
  - 兩個按鈕：SET INT32_MAX（設定最大值）/ ∞ 無限疊加（疊加）
  - 操作後呼叫 `fetchWallet()` 同步餘額顯示
- `frontend/src/styles.css`：新增 `.dev-cheat-*` 樣式（琥珀色警示風格）

## 原因

測試階段需要快速補充 coin 驗證掃描功能，避免每次都要手動打後台或操作 Django Admin。

## 影響範圍

- 端點有 `DEBUG=True` 守門，`DEBUG=False`（production）直接回傳 403
- 面板僅登入狀態才顯示，未登入使用者看不到
- `CoinTransaction` 會寫入 `type=manual`、`note="[DEV CHEAT]"`，稽核軌跡可追蹤

## 上線前必須移除

- [ ] `backend/apps/billing/urls.py`：刪除 `path("dev-cheat/", ...)` 這一行
- [ ] `backend/apps/billing/views.py`：刪除 `dev_cheat_coins` 函式與 `_INT32_MAX`
- [ ] `frontend/src/App.jsx`：刪除 `handleCheat`、`cheatLoading`、`cheatMsg` state 及 dev-cheat-panel section
- [ ] `frontend/src/styles.css`：刪除 `.dev-cheat-*` 樣式區塊

## 驗證方式

- `uv run python backend/manage.py check` → 0 issues ✅
- `uv run python backend/manage.py test apps.billing` → 32 tests passed ✅
