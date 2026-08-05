# 啟用綠界 Stage 測試購點

**日期**：2026-08-05
**操作者**：Codex

## 變更內容

- 將 K8s 金流模式切換為 `ecpay_test`，固定使用綠界 Stage 結帳端點與公開 HTTPS callback。
- 在 Secret 範本補上三個綠界必要鍵的空白欄位，真值仍只允許存在 live Secret。
- 更新 web／worker Pod template 的 config revision annotation，確保 ConfigMap 變更會觸發 rollout。
- 補充 Stage 啟用順序、驗證條件與回滾方式。

## 原因

購點程式碼已存在於 `origin/main`，但正式 GitOps ConfigMap 維持 `disabled`，因此網站購點頁不接受訂單。這次只啟用不會真實扣款的綠界 Stage 測試流程。

## 影響範圍

- K8s migrate、web、worker 會在 Argo CD 同步時重新讀取金流設定。
- 購點頁將允許建立 Stage pending 訂單並導向綠界測試頁。
- 推送前必須先確認 live `argus-secret` 的三個綠界鍵存在且非空，否則 Django 會拒絕啟動。

## 驗證方式

- `uv run python backend/manage.py check`：通過，0 issues。
- `uv run python backend/manage.py test apps.billing`：45 項通過。
- Kustomize／K8s runtime 合約測試：22 項通過。
- 本機 runserver 直打 `/api/billing/plans/`：HTTP 200、`payment_mode=ecpay_test`、`purchase_enabled=true`、4 個啟用方案。
- 正式叢集 Secret、Argo rollout 與 Stage 端到端交易仍須在 push 前後依啟用順序驗證。
