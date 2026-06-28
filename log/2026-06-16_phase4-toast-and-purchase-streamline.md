# 2026-06-16 Phase 4：公告 toast 分流 + /purchase 行銷頁簡化

> 接續 `log/2026-06-15_resend-smtp-verified.md`。完成審計剩餘的 B1 + B4 兩項。

## 變更內容

### B1：公告 toast / modal 分流

| 檔案 | 改動 |
|---|---|
| [App.jsx:2774-2812](frontend/src/App.jsx:2774) | 新增 `AnnouncementToast` 元件：右下角、堆疊、5 秒自動消失、滑鼠 hover 暫停、`prefers-reduced-motion` 尊重 |
| [App.jsx:2827-2829](frontend/src/App.jsx:2827) | `DashboardPage` 拆兩個 state：`announcements` (permanent → modal) / `toasts` (temporary → toast) |
| [App.jsx:2860-2872](frontend/src/App.jsx:2860) | 載入公告後依 `type` 分流：`temporary` → setToasts；`permanent` → setAnnouncements |
| [App.jsx:2883](frontend/src/App.jsx:2883) | `handleDismiss` 同時清 toasts 與 announcements，避免 dismiss 後狀態不一致 |
| [App.jsx:3052](frontend/src/App.jsx:3052) | 在 dashboard 底部 render `AnnouncementToast` |
| [styles.css](frontend/src/styles.css) | 新增 `.argus-toast-stack` / `.argus-toast` / `.argus-toast-body` / `.argus-toast-close` + slide-in keyframe |

### B4：/purchase 與 /billing IA 重複消除

| 檔案 | 改動 |
|---|---|
| [App.jsx:4922-5024](frontend/src/App.jsx:4922) | `PurchasePage` 刪除「方案一覽」section（消除跟 `/billing` step 1 重複）；移除 `plans` state + fetch；hero eyebrow 從 `PURCHASE · 購買方案` 改 `PRICING · 為什麼選 Argus`；hero 加 CTA「看方案 + 開始結帳」navigate `/billing` |

剩下保留：hero / 為什麼選 Argus 對比表 / 常見問題 / 最終 CTA「準備好了嗎」。

## 原因

### B1 toast 分流
公告 `AnnouncementModal` 對 `temporary` 跟 `permanent` 一視同仁用中央 modal，**小事也阻斷使用流**。業界做法：
- `permanent`（要求確認）→ 保留中央 modal
- `temporary`（純通知）→ 改右下角 toast，自動消失、不阻斷操作

### B4 路由整合
`/purchase` 和 `/billing` step 1 都顯示完整 4 個方案卡 → 使用者體驗「為什麼同樣方案要看兩次？」。`PurchasePage` 改成「純行銷頁」（為什麼選 Argus + FAQ + CTA），`BillingPage` 變唯一的「方案 + 結帳」入口。兩個路由各司其職。

## 影響範圍

- 前端：`App.jsx` + `styles.css`，無後端 / DB 改動
- B4 拿掉的「方案展示」內容，在 `/billing` step 1 仍可看到（含「≈ N 個小型網站」等價說明、選此方案 CTA）
- 使用者體驗變化：`/purchase` 不再有方案卡，但 hero CTA 一鍵跳 `/billing` 開始選方案

## 驗證

| 項 | 結果 |
|---|---|
| `npm run build` | ✅ 268 modules 3.23s |
| `manage.py check` | ✅（merge 後已驗證、本次無後端改動） |
| toast 樣式（hover 暫停 / 5s 自動消失 / 動畫尊重 reduced-motion） | code 實作通過 review，待實機驗證 |
| `/purchase` 結構 | hero + 對比表 + FAQ + 最終 CTA（已 grep 確認、無殘留方案展示） |

## 「AI 味」自查

| 項 | 結果 |
|---|---|
| toast 配色 | cyan (`#67e8f9` / `#22d3ee`) + slate dark，沿用既有 token，無亮白 / 紫漸層 |
| 動畫 | slide-in 0.22s ease，單一動效不堆 |
| 文案 | `「準備好了嗎？」` `「3 步驟結帳，30 秒入帳」` `「看方案 + 開始結帳 →」` — 工具人語氣 |
| 違規 emoji 堆 | 0 個 |

## 待做（之前列、本次未動）

- A2 DMARC（你去 Resend 點自動配置，5 分鐘）
- A4 體驗方案 NT$50 / 60 coin（你去 `/admin/plans` 自己加，5 分鐘）
- B2 sort_order 上下移按鈕
- B3 AdminCmsManager 對 TeamMember `skill_levels` / `contributions` 物件陣列支援
- A1 公網機部署（git pull + .env 加 EMAIL 區塊）
