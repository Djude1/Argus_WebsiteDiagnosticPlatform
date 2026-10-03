# 同步回收掃描 Job 的網路策略合約測試

**日期**：2026-10-03
**操作者**：Codex

## 變更內容
- 將 `app=reap` 納入既有 PostgreSQL Ingress NetworkPolicy 合約測試。
- 移除重複的 root manifest 測試，保留 backend scans 模組的單一權威合約。

## 原因
首次修復已更新 manifest，但未同步既有的精確 app 白名單測試，導致 Quality Gate 失敗。

## 影響範圍
- 只影響 K8s NetworkPolicy 的測試預期。
- 不擴大 PostgreSQL 的實際連線權限。

## 驗證方式
- 執行完整 backend 測試與 K8s manifest 契約測試。
