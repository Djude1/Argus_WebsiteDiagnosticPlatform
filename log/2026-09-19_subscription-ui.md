# 訂閱方案使用者端 UI（BillingPage＋SettingsPage）

- **日期**：2026-09-19
- **操作者**：ZCode（subagent 實作，main 驗收）

## 變更內容

- `frontend/src/api.js`：新增 `fetchSubscriptionPlans()`／`fetchMySubscription()`／`subscribePlan(planCode)`／`cancelSubscription()`（對應 backend `subscription/*` 四端點）
- `frontend/src/features/account/AuthenticatedPages.jsx`：
  - 新增 `SubscriptionPanel` 元件——BillingPage 改為「月訂閱方案」面板（上）＋「單次購買點數」wizard（下）的對比版面；方案卡顯示月費/每月點數/換算率/「比單次購點最划算方案再多 N% 點」動態比較/features/badge；有訂閱時顯示狀態卡（方案、生效中/已取消/已到期徽章、剩餘期數、下次贈點日）與取消流程
  - 訂閱/取消走專案現成 `useConfirmDialogs()`（取消確認文案說明「當期權益保留到期滿」）；成功後重抓錢包與訂閱狀態；付費關閉（503）顯示後端繁中訊息
  - SettingsPage「點數錢包」後新增「訂閱狀態」小卡（沿用 settings-section 既有 class；無訂閱→「前往訂閱」連 /billing）
- `frontend/src/styles.css`：新增 `.billing-sub-*` 系列樣式（重用購點面板材質與 token，無新設計語言）

## 原因

- 複賽評審問題 3（「訂閱機制要把它放進系統」）：backend 訂閱 API（commit 6ab4a7a）完成後補齊使用者端 UI，讓「月訂閱 vs 單次購點」在結帳頁一目了然（demo 展示點）。

## 影響範圍

- 僅前端三檔；不改 backend、不改 admin 頁（admin 訂閱管理介面屬後續 wave）。

## 驗證方式

- `cd frontend; .\build-node22.ps1` 成功（✓ built in 27.54s，2044 modules，無 chunk 超過 500 kB）
- API 欄位名以 backend serializers/views 程式碼逐項查證（plans 回應含 payment_mode/subscribe_enabled；subscription 含 status_label/periods_remaining 等）
- 已載入 argus-ui-design skill 並遵循（重用既有 class 與 confirm 對話框；全部文字繁中）
